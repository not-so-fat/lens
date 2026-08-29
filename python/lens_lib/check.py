"""Shared Stop/stop hook check logic (F3 / F5.4).

The loop is deliberately simple: a stop with an unmet obligation blocks, and
keeps blocking, until the obligation is resolved. An obligation has exactly two
legitimate exits, and the hook only ever checks the run log for one of them:

  1. a ``lens_run`` was logged for the session (the review happened), or
  2. a ``lens_skip`` was logged for the session (the owner deliberately held).

Two things create an obligation:

  * a **watched-file write** with no matching lens_run/lens_skip, or
  * an **explicit lens invocation** in the prompt ("arming", F3.5) — so a
    chat deliverable that never wrote a file still gets reviewed.

That shared second exit is why there are no circuit breakers, TTLs, or block
counters here: the loop keeps looping until one of two *recorded, intentional*
things happens. "Hold this one" is a real action the worker takes on the
owner's say-so, not a heuristic the hook has to guess.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .config import Config, ConfigError, resolve_config
from .log import (
    append_record,
    has_lens_run_for_sessions,
    has_lens_skip_for_sessions,
    latest_gate_ts,
    latest_lens_run_ts,
    latest_lens_skip_ts,
)
from .paths import BUILTIN_IGNORE_GLOBS, filter_watched, load_lensignore
from .transcript import gather_writes, prune_sidechannel_file, session_id_from_transcript
from .util import (
    INVOCATION_TEMPLATE,
    SKIP_TEMPLATE,
    conversation_workspace_writes_path,
    session_armed_path,
    session_writes_path,
    utc_now_iso,
    workspace_writes_path,
)


@dataclass
class CheckResult:
    watched_writes: bool
    lens_run_found: bool
    blocked: bool
    enforce: bool
    session: str
    duration_ms: float
    host: str
    message: str
    watched_paths: List[str] = field(default_factory=list)
    declined: bool = False
    armed: bool = False


def _real_ids(ids: List[str]) -> List[str]:
    return [i for i in ids if i and i != "unknown"]


# --- Explicit-invocation arming (F3.5) -----------------------------------
# A chat deliverable never writes a watched file, so the write-triggered gate
# cannot catch "use <lens>". When the user explicitly asks for the lens, a
# UserPromptSubmit hook arms the session; the Stop hook then requires a lens_run
# (or a lens_skip) regardless of writes. Arming reuses the same loop and the
# same two exits — there is no separate warn-first / breaker / TTL machinery.

# Negations / hedges that flip an otherwise-matching phrase ("don't use the lens").
# The contraction alternative requires the apostrophe so ordinary words ending in
# "nt" (want, important, current, different) are NOT treated as negations.
_NEG_RE = re.compile(
    r"(?:\b(?:no|not|never|without|avoid|skip|cannot)\b|\binstead\s+of\b|n['’]t\b)",
    re.IGNORECASE,
)
_VERB = r"use|using|run|running|apply|applying|invoke|execute|redo\w*"

# Arming must read the user's LIVE instruction, not machine-injected or quoted
# content. Two harness wrappers saturate the prompt with lens phrasing that is
# not a request: transcript-distillation prompts fenced with BEGIN/END SESSION
# TRANSCRIPT, and <task-notification> completion notices. Strip both first.
_FENCE_BEGIN = re.compile(r"={3,}\s*BEGIN SESSION TRANSCRIPT\b", re.IGNORECASE)
_FENCE_END = re.compile(r"={3,}\s*END SESSION TRANSCRIPT\s*={3,}", re.IGNORECASE)
_TASK_NOTIF = re.compile(
    r"<task-notification>.*?(?:</task-notification>|\Z)", re.IGNORECASE | re.DOTALL
)


def _strip_transcript_blocks(text: str) -> str:
    begin = _FENCE_BEGIN.search(text)
    if not begin:
        return text
    last_end = None
    for m in _FENCE_END.finditer(text):
        if m.start() >= begin.start():
            last_end = m
    if last_end is not None:
        return text[: begin.start()] + "\n" + text[last_end.end():]
    return text[: begin.start()]


def _strip_injected_blocks(text: str) -> str:
    """Remove harness-injected / quoted wrappers so arming sees only live text."""
    return _TASK_NOTIF.sub(" ", _strip_transcript_blocks(text))


# "lens doctor" / "lens close" are lens *tooling*, not a request to run the
# review lens — a match ending in "lens" followed by one of these must not arm.
_TOOLING_AFTER = re.compile(
    r"[-\s]+doctor\b|-+close\b|-+skip\b|\s+close\s+command\b", re.IGNORECASE
)


def _negated_before(text: str, idx: int) -> bool:
    return _NEG_RE.search(text[max(0, idx - 20):idx]) is not None


def is_lens_invocation(prompt: str, known_names: Sequence[str] = ()) -> bool:
    """
    True if the prompt explicitly and affirmatively asks to run the lens.

    Rejects negations/hedges ("don't use the lens", "without using the lens"),
    unrelated senses ("eyeglasses lens metaphor"), and lens phrasing quoted
    inside a fenced raw transcript or a <task-notification> wrapper.
    """
    if not isinstance(prompt, str) or not prompt:
        return False
    prompt = _strip_injected_blocks(prompt)
    # `(?!)` never matches — so name-based patterns are inert when no names.
    name_alt = "|".join(re.escape(n) for n in known_names if n) or r"(?!)"
    patterns = (
        r"\blens\s*=\s*\S",
        rf"\b(?:{_VERB})\s+(?:the\s+|(?:{name_alt})\s+)?lens\b",
        r"\blens\s+(?:loop|review)\b",
        rf"\bwith\s+(?:{name_alt})\s+lens\b",
        rf"\b(?:{_VERB})\s+(?:with\s+|the\s+)?(?:{name_alt})\b",
        rf"\b(?:{name_alt})\s+lens\b",
    )
    for pat in patterns:
        for m in re.finditer(pat, prompt, re.IGNORECASE):
            if _negated_before(prompt, m.start()):
                continue
            # Window must fit the longest tooling suffix (" close command").
            if _TOOLING_AFTER.match(prompt[m.end():m.end() + 24]):
                continue
            return True
    return False


def arm_session(session: str, *, ts: Optional[str] = None, reason: str = "explicit-invocation") -> None:
    """Mark a session as requiring a lens_run (or lens_skip) before it may stop."""
    if not session or session == "unknown":
        return
    path = session_armed_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{ts or utc_now_iso()}\t{reason}\n", encoding="utf-8")


def read_arm_ts(session: str) -> Optional[str]:
    """Return the arm timestamp for a session, or None if not armed."""
    if not session or session == "unknown":
        return None
    path = session_armed_path(session)
    if not path.is_file():
        return None
    try:
        first = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
    except (OSError, IndexError):
        return None
    ts = first.split("\t", 1)[0].strip()
    return ts or None


def disarm_session(session: str) -> None:
    if not session:
        return
    try:
        session_armed_path(session).unlink()
    except OSError:
        pass


def run_check(
    *,
    host: str,
    transcript_path: Optional[str] = None,
    session_id: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    config: Optional[Config] = None,
) -> CheckResult:
    """Evaluate whether this turn must invoke the lens runner before stopping.

    Blocks while the session has an unmet obligation (a watched write, or an
    explicit lens invocation) with no matching ``lens_run`` and no matching
    ``lens_skip``. The block persists across stops (a true loop) until one of
    those two records lands.
    """
    started = time.perf_counter()
    cwd = cwd or os.getcwd()
    ids: List[str] = []
    for sid in session_ids or []:
        if sid and str(sid) not in ids:
            ids.append(str(sid))
    if session_id and str(session_id) not in ids:
        ids.insert(0, str(session_id))
    session = ids[0] if ids else (
        session_id_from_transcript(transcript_path) if transcript_path else "unknown"
    )
    if session and session not in ids:
        ids.append(session)

    try:
        cfg = config or resolve_config()
    except ConfigError as e:
        duration_ms = (time.perf_counter() - started) * 1000
        msg = f"Lens config unresolved; enforcement skipped.\n{e}"
        return CheckResult(
            watched_writes=False,
            lens_run_found=False,
            blocked=False,
            enforce=False,
            session=session,
            duration_ms=duration_ms,
            host=host,
            message=msg,
        )

    side_paths: List[str] = [str(session_writes_path(sid)) for sid in ids if sid]
    real = _real_ids(ids)
    try:
        if real:
            for sid in real:
                side_paths.append(str(conversation_workspace_writes_path(cwd, sid)))
        else:
            side_paths.append(str(workspace_writes_path(cwd)))
    except OSError:
        pass

    # Cursor: ignore side-channel writes already covered by a session lens_run
    # or lens_skip (NOT-41: skip must advance the freshness window too).
    after_ts = None
    if not transcript_path and real:
        after_ts = latest_gate_ts(cfg.log_path, real)

    # Routine files a repo/config marked non-deliverable never trip the write gate.
    ignore_globs = [
        *BUILTIN_IGNORE_GLOBS,
        *cfg.ignore_globs,
        *load_lensignore(cwd),
    ]

    # Full session activity (for M3 metric) — ignore after_ts.
    written_all, _ = gather_writes(
        transcript_path,
        sidechannel_paths=side_paths,
        watch_globs=cfg.watch_globs,
        after_ts=None,
    )
    watched_all, excluded_count = filter_watched(
        written_all, cfg.watch_globs, cwd, ignore_globs=ignore_globs
    )
    wrote_watched = len(watched_all) > 0

    written, first_ts = gather_writes(
        transcript_path,
        sidechannel_paths=side_paths,
        watch_globs=cfg.watch_globs,
        after_ts=after_ts,
    )
    watched, _ = filter_watched(
        written, cfg.watch_globs, cwd, ignore_globs=ignore_globs
    )
    watched_writes = len(watched) > 0
    allow_untagged = bool(transcript_path)

    # --- Writes gate ---
    lens_run_found = False
    writes_declined = False
    gate = "none"
    if watched_writes:
        ids_for_gate = real or ([session] if session and session != "unknown" else [])
        if has_lens_run_for_sessions(
            cfg.log_path, ids_for_gate, since_iso=first_ts, allow_untagged=allow_untagged
        ):
            lens_run_found = True
            gate = "session"
        elif has_lens_skip_for_sessions(
            cfg.log_path, ids_for_gate, since_iso=first_ts, allow_untagged=allow_untagged
        ):
            writes_declined = True
            gate = "declined"
    elif wrote_watched and after_ts and real:
        # Cursor: writes existed but all fall at/before the latest gate satisfaction.
        skip_ts = latest_lens_skip_ts(cfg.log_path, real)
        if skip_ts and skip_ts == after_ts:
            writes_declined = True
            gate = "declined"
        else:
            lens_run_found = True
            gate = "session"

    unsatisfied_writes = watched_writes and not lens_run_found and not writes_declined

    # --- Arm gate (explicit invocation) ---
    armed_ts: Optional[str] = None
    for sid in real:
        a = read_arm_ts(sid)
        if a and (armed_ts is None or a < armed_ts):
            armed_ts = a
    armed = armed_ts is not None
    armed_by_run = False
    arm_declined = False
    if armed:
        armed_by_run = has_lens_run_for_sessions(
            cfg.log_path, real, since_iso=armed_ts, allow_untagged=allow_untagged
        )
        if not armed_by_run:
            arm_declined = has_lens_skip_for_sessions(
                cfg.log_path, real, since_iso=armed_ts, allow_untagged=allow_untagged
            )
    armed_satisfied = armed_by_run or arm_declined
    declined = writes_declined or arm_declined

    block_writes = bool(cfg.enforce and unsatisfied_writes)
    block_armed = bool(cfg.enforce and armed and not armed_satisfied)
    should_block = block_writes or block_armed

    sess_hint = (
        f" Ensure the lens_run includes session={session!r} "
        "(or omit session only on Claude Bash appends)."
        if host == "claude-code"
        else f" Ensure the lens_run includes session={session!r}."
    )
    skip_hint = (
        " If the owner told you to hold this one, record a skip instead so the "
        f"loop stops without a review: {SKIP_TEMPLATE}"
    )
    if block_writes:
        message = (
            "Lens enforcement: this session wrote watched files but no matching "
            f"lens_run was logged at or after the session start ({first_ts or 'unknown'})."
            f"{sess_hint} {INVOCATION_TEMPLATE}{skip_hint} "
            f"Watched writes: {', '.join(watched[:8])}"
            + ("…" if len(watched) > 8 else "")
        )
    elif block_armed:
        message = (
            "Lens enforcement: you invoked the lens for this session but no matching "
            f"lens_run has been logged since you asked ({armed_ts})."
            f"{sess_hint} {INVOCATION_TEMPLATE}{skip_hint}"
        )
    elif (unsatisfied_writes or (armed and not armed_satisfied)) and not cfg.enforce:
        message = (
            "Warning: this session has a pending lens review "
            f"(enforce=false).{sess_hint} {INVOCATION_TEMPLATE}"
        )
    else:
        message = ""

    # A satisfied arm is consumed so later chat turns are not re-blocked.
    if armed and armed_satisfied:
        for sid in real:
            disarm_session(sid)

    # Prune consumed side-channel lines after gate satisfaction (Cursor).
    if (lens_run_found or writes_declined) and not transcript_path:
        prune_at = latest_gate_ts(cfg.log_path, real) or first_ts
        for sc in side_paths:
            try:
                prune_sidechannel_file(sc, after_ts=prune_at)
            except OSError:
                pass

    duration_ms = (time.perf_counter() - started) * 1000

    skip_reason = None
    if declined:
        skip_reason = "declined"
    elif (unsatisfied_writes or (armed and not armed_satisfied)) and not cfg.enforce:
        skip_reason = "enforce_false"
    elif not watched_writes and not armed and written_all and not wrote_watched:
        skip_reason = "no_watch_match"
    elif excluded_count and not wrote_watched and not armed:
        skip_reason = "excluded_only"

    record: Dict[str, Any] = {
        "ts": utc_now_iso(),
        "event": "hook_check",
        "session": session,
        "session_ids": ids,
        "watched_writes": watched_writes,
        "wrote_watched": wrote_watched,
        "armed": armed,
        "lens_run_found": lens_run_found,
        "declined": declined,
        "blocked": should_block,
        "enforce": cfg.enforce,
        "gate": gate,
        "excluded_writes": excluded_count,
        "duration_ms": round(duration_ms, 3),
        "host": host,
    }
    if skip_reason:
        record["skip_reason"] = skip_reason
    try:
        append_record(cfg.log_path, record)
    except OSError:
        pass

    return CheckResult(
        watched_writes=watched_writes,
        lens_run_found=lens_run_found,
        blocked=should_block,
        enforce=cfg.enforce,
        session=session,
        duration_ms=duration_ms,
        host=host,
        message=message,
        watched_paths=watched,
        declined=declined,
        armed=armed,
    )


def record_sidechannel_write(
    session: str,
    file_path: str,
    *,
    workspace_root: Optional[str] = None,
) -> None:
    """
    Record a write for later stop-hook gather.

    Prefer (workspace, conversation_id). Workspace-wide fallback only when
    session is missing/unknown (I-3).
    """
    targets = [session_writes_path(session)]
    if workspace_root:
        try:
            if session and session != "unknown":
                targets.append(
                    conversation_workspace_writes_path(workspace_root, session)
                )
            else:
                targets.append(workspace_writes_path(workspace_root))
        except OSError:
            pass
    line = f"{utc_now_iso()}\t{file_path}\n"
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
