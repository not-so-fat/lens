"""Shared Stop/stop hook check logic (F3 / F5.4)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config, ConfigError, resolve_config
from .log import (
    append_record,
    has_lens_run_for_sessions,
    has_lens_run_since,
    latest_lens_run_ts,
)
from .paths import filter_watched
from .transcript import gather_writes, prune_sidechannel_file, session_id_from_transcript
from .util import (
    INVOCATION_TEMPLATE,
    conversation_workspace_writes_path,
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
    watched_paths: List[str]


def _real_ids(ids: List[str]) -> List[str]:
    return [i for i in ids if i and i != "unknown"]


def run_check(
    *,
    host: str,
    transcript_path: Optional[str] = None,
    session_id: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    config: Optional[Config] = None,
) -> CheckResult:
    """Evaluate whether this turn must invoke the lens runner before stopping."""
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
            watched_paths=[],
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

    # Cursor: ignore side-channel writes already covered by a session lens_run.
    after_ts = None
    if not transcript_path and real:
        after_ts = latest_lens_run_ts(cfg.log_path, real)

    # Full session activity (for M3 metric) — ignore after_ts.
    written_all, _ = gather_writes(
        transcript_path,
        sidechannel_paths=side_paths,
        watch_globs=cfg.watch_globs,
        after_ts=None,
    )
    watched_all, excluded_count = filter_watched(
        written_all, cfg.watch_globs, cwd
    )
    wrote_watched = len(watched_all) > 0

    written, first_ts = gather_writes(
        transcript_path,
        sidechannel_paths=side_paths,
        watch_globs=cfg.watch_globs,
        after_ts=after_ts,
    )
    watched, _ = filter_watched(written, cfg.watch_globs, cwd)
    watched_writes = len(watched) > 0
    lens_run_found = False
    gate = "none"
    if watched_writes:
        # pass and escalated terminal lens_run records both satisfy the gate.
        if transcript_path:
            # Claude F3.1: transcript time window (session == transcript).
            if has_lens_run_since(cfg.log_path, first_ts):
                lens_run_found = True
                gate = "time"
            elif has_lens_run_for_sessions(
                cfg.log_path, real, since_iso=first_ts
            ):
                lens_run_found = True
                gate = "session"
        else:
            # Cursor: session-scoped only — never a global time gate (cross-chat leak).
            if has_lens_run_for_sessions(
                cfg.log_path, real, since_iso=first_ts
            ):
                lens_run_found = True
                gate = "session"
    elif wrote_watched and after_ts and real:
        # Cursor: writes existed but all fall at/before the latest session lens_run.
        lens_run_found = True
        gate = "session"

    should_block = bool(cfg.enforce and watched_writes and not lens_run_found)
    if not watched_writes:
        message = ""
    elif lens_run_found:
        message = ""
    elif not cfg.enforce:
        message = (
            "Warning: watched deliverable writes in this session have no lens_run "
            f"(enforce=false). {INVOCATION_TEMPLATE}"
        )
    else:
        message = (
            "Lens enforcement: this session wrote watched files but no lens_run "
            f"was logged at or after the session start ({first_ts or 'unknown'}). "
            f"{INVOCATION_TEMPLATE} "
            f"Watched writes: {', '.join(watched[:8])}"
            + ("…" if len(watched) > 8 else "")
        )

    # Prune consumed side-channel lines after a satisfying run (Cursor).
    if lens_run_found and not transcript_path:
        prune_at = latest_lens_run_ts(cfg.log_path, real) or first_ts
        for sc in side_paths:
            try:
                prune_sidechannel_file(sc, after_ts=prune_at)
            except OSError:
                pass

    duration_ms = (time.perf_counter() - started) * 1000

    skip_reason = None
    if watched_writes and not cfg.enforce:
        skip_reason = "enforce_false"
    elif not watched_writes and written_all and not wrote_watched:
        skip_reason = "no_watch_match"
    elif excluded_count and not wrote_watched:
        skip_reason = "excluded_only"

    record: Dict[str, Any] = {
        "ts": utc_now_iso(),
        "event": "hook_check",
        "session": session,
        "session_ids": ids,
        "watched_writes": watched_writes,
        "wrote_watched": wrote_watched,
        "lens_run_found": lens_run_found,
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
