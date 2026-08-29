"""Append-only JSONL run log at config log_path."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .util import utc_now_iso

CHECK_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RUN_ID_RE = re.compile(r"^lr_[a-f0-9]+$")
FINDING_KEYS = frozenset(
    {"round", "check", "target", "severity", "reaction", "note", "class"}
)
VALID_VERDICTS = frozenset({"pass", "escalated", "held"})
VALID_REACTIONS = frozenset(
    {"fixed", "fixed-class", "disputed", "escalated", "pending-owner"}
)


class AmbiguousCloseError(ValueError):
    """Deliverable-only close matched more than one lens_run."""

    def __init__(self, message: str, candidates: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.candidates = candidates


def new_run_id() -> str:
    return f"lr_{secrets.token_hex(8)}"


def ensure_log(log_path: Path) -> Path:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()
    return log_path


def append_record(log_path: Path, record: Dict[str, Any]) -> Path:
    """Append one complete JSONL line. Adds ts if missing."""
    if "ts" not in record:
        record = {**record, "ts": utc_now_iso()}
    path = ensure_log(log_path)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def iter_records(log_path: Path) -> Iterator[Dict[str, Any]]:
    if not log_path.is_file():
        return
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def parse_iso_ts(value: str) -> Optional[datetime]:
    """Parse ISO-8601 timestamps (Z, offset, fractional) to UTC datetimes."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def has_lens_run_since(log_path: Path, since_iso: Optional[str]) -> bool:
    """
    True if any lens_run has ts >= since_iso (instant compare).

    Fail closed when since_iso is None or unparseable — never treat an
    unbounded / broken window as satisfied by a historical run.
    Any terminal verdict (pass, escalated, held) satisfies the gate.
    """
    since = parse_iso_ts(since_iso) if since_iso else None
    if since is None:
        return False
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run":
            continue
        ts = parse_iso_ts(str(rec.get("ts") or ""))
        if ts is not None and ts >= since:
            return True
    return False


def _lens_run_session_ids(rec: Dict[str, Any]) -> set:
    ids = set()
    if rec.get("session"):
        ids.add(str(rec["session"]))
    for sid in rec.get("session_ids") or []:
        if sid:
            ids.add(str(sid))
    return ids


def _has_event_for_sessions(
    log_path: Path,
    session_ids: Sequence[str],
    event: str,
    *,
    since_iso: Optional[str] = None,
    allow_untagged: bool = False,
) -> bool:
    """
    True if a record of ``event`` satisfies this session's gate.

    - Tagged with this session (or conversation) id, or
    - Untagged (no session fields) when allow_untagged=True — forgives Claude
      Bash-appended records that omit session; still rejects records tagged for
      a *different* session (keeps cross-chat leak closed).

    Optional since_iso requires ts ≥ that instant.
    """
    wanted = {str(s) for s in session_ids if s and s != "unknown"}
    if not wanted and not allow_untagged:
        return False
    since = parse_iso_ts(since_iso) if since_iso else None
    for rec in iter_records(log_path):
        if rec.get("event") != event:
            continue
        rec_ids = _lens_run_session_ids(rec)
        if rec_ids:
            if not wanted or not (rec_ids & wanted):
                continue
        elif not allow_untagged:
            continue
        if since is None:
            return True
        ts = parse_iso_ts(str(rec.get("ts") or ""))
        if ts is not None and ts >= since:
            return True
    return False


def has_lens_run_for_sessions(
    log_path: Path,
    session_ids: Sequence[str],
    *,
    since_iso: Optional[str] = None,
    allow_untagged: bool = False,
) -> bool:
    """True if a lens_run satisfies this session's gate (any terminal verdict)."""
    return _has_event_for_sessions(
        log_path, session_ids, "lens_run",
        since_iso=since_iso, allow_untagged=allow_untagged,
    )


def has_lens_skip_for_sessions(
    log_path: Path,
    session_ids: Sequence[str],
    *,
    since_iso: Optional[str] = None,
    allow_untagged: bool = False,
) -> bool:
    """True if a lens_skip (owner deliberately held) satisfies this session's gate."""
    return _has_event_for_sessions(
        log_path, session_ids, "lens_skip",
        since_iso=since_iso, allow_untagged=allow_untagged,
    )


def _latest_event_ts(
    log_path: Path,
    event: str,
    session_ids: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Latest ts for ``event``, optionally restricted to matching session ids."""
    wanted = None
    if session_ids is not None:
        wanted = {str(s) for s in session_ids if s and s != "unknown"}
        if not wanted:
            return None
    latest: Optional[datetime] = None
    latest_raw: Optional[str] = None
    for rec in iter_records(log_path):
        if rec.get("event") != event:
            continue
        if wanted is not None:
            rec_ids = _lens_run_session_ids(rec)
            if not (rec_ids & wanted):
                continue
        raw = str(rec.get("ts") or "")
        ts = parse_iso_ts(raw)
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
            latest_raw = raw
    return latest_raw


def latest_lens_run_ts(
    log_path: Path, session_ids: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Latest lens_run ts, optionally restricted to matching session ids."""
    return _latest_event_ts(log_path, "lens_run", session_ids)


def latest_lens_skip_ts(
    log_path: Path, session_ids: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Latest lens_skip ts, optionally restricted to matching session ids."""
    return _latest_event_ts(log_path, "lens_skip", session_ids)


def latest_gate_ts(
    log_path: Path, session_ids: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Latest gate-satisfying ts (lens_run or lens_skip) for session ids."""
    run_ts = latest_lens_run_ts(log_path, session_ids)
    skip_ts = latest_lens_skip_ts(log_path, session_ids)
    if run_ts is None:
        return skip_ts
    if skip_ts is None:
        return run_ts
    run_dt = parse_iso_ts(run_ts)
    skip_dt = parse_iso_ts(skip_ts)
    if run_dt is None:
        return skip_ts
    if skip_dt is None:
        return run_ts
    return run_ts if run_dt >= skip_dt else skip_ts


def latest_lens_skip_for_sessions(
    log_path: Path,
    session_ids: Sequence[str],
    *,
    since_iso: Optional[str] = None,
    deliverable: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Most recent lens_skip for session ids (by ts), optionally since since_iso."""
    wanted = {str(s) for s in session_ids if s and s != "unknown"}
    if not wanted:
        return None
    since = parse_iso_ts(since_iso) if since_iso else None
    latest: Optional[datetime] = None
    latest_rec: Optional[Dict[str, Any]] = None
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_skip":
            continue
        if deliverable is not None and rec.get("deliverable") != deliverable:
            continue
        rec_ids = _lens_run_session_ids(rec)
        if not (rec_ids & wanted):
            continue
        raw = str(rec.get("ts") or "")
        ts = parse_iso_ts(raw)
        if ts is None:
            continue
        if since is not None and ts < since:
            continue
        if latest is None or ts > latest:
            latest = ts
            latest_rec = rec
    return latest_rec


def is_duplicate_lens_run(
    log_path: Path, record: Dict[str, Any], *, window_seconds: int = 120
) -> bool:
    """
    True if a terminal lens_run with the same identity was already logged.

    Guards the append path against a redundant re-log: a spurious gate re-block
    (e.g. an arming re-fire) can prompt the worker to append the *same* run again
    ~a minute later — same findings, new ts. Identity = same deliverable + rounds
    and either a shared session id, or — when *both* sides are untagged — the same
    verdict within window_seconds. Mixed tagged/untagged is never a duplicate
    (cannot prove they are the same session). Two different sessions reviewing the
    same deliverable/round are NOT duplicates.
    """
    if record.get("event") != "lens_run":
        return False
    if record.get("run_id"):
        for rec in iter_records(log_path):
            if rec.get("event") == "lens_run" and rec.get("run_id") == record.get("run_id"):
                return True
    deliverable = record.get("deliverable")
    rounds = record.get("rounds")
    if deliverable is None or rounds is None:
        return False
    new_ids = _lens_run_session_ids(record)
    new_ts = parse_iso_ts(str(record.get("ts") or ""))
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run":
            continue
        if rec.get("deliverable") != deliverable or rec.get("rounds") != rounds:
            continue
        prev_ids = _lens_run_session_ids(rec)
        if new_ids and prev_ids:
            if new_ids & prev_ids:
                return True
            continue  # different session, same deliverable/round — not a dup
        if new_ids or prev_ids:
            # Exactly one side tagged — cannot equate sessions; not a dup.
            continue
        if rec.get("verdict") != record.get("verdict"):
            continue
        prev_ts = parse_iso_ts(str(rec.get("ts") or ""))
        if new_ts is None or prev_ts is None:
            continue  # unparseable ts — do not over-dedup
        if abs((new_ts - prev_ts).total_seconds()) <= window_seconds:
            return True
    return False


def deliverable_has_lens_run(log_path: Path, deliverable: str) -> bool:
    for rec in iter_records(log_path):
        if rec.get("event") == "lens_run" and rec.get("deliverable") == deliverable:
            return True
    return False


def latest_lens_run_for_deliverable(
    log_path: Path, deliverable: str
) -> Optional[Dict[str, Any]]:
    """Most recent lens_run for a deliverable key (by ts)."""
    runs = list_lens_runs_for_deliverable(log_path, deliverable)
    return runs[0] if runs else None


def get_lens_run_by_id(log_path: Path, run_id: str) -> Optional[Dict[str, Any]]:
    for rec in iter_records(log_path):
        if rec.get("event") == "lens_run" and rec.get("run_id") == run_id:
            return rec
    return None


def list_lens_runs_for_deliverable(
    log_path: Path, deliverable: str
) -> List[Dict[str, Any]]:
    """All lens_run rows for a deliverable, newest first."""
    runs: List[Dict[str, Any]] = []
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run" or rec.get("deliverable") != deliverable:
            continue
        runs.append(rec)

    def sort_key(rec: Dict[str, Any]) -> datetime:
        ts = parse_iso_ts(str(rec.get("ts") or ""))
        if ts is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return ts

    runs.sort(key=sort_key, reverse=True)
    return runs


def human_review_exists_for_run(log_path: Path, run_id: str) -> bool:
    for rec in iter_records(log_path):
        if rec.get("event") != "human_review":
            continue
        if rec.get("lens_run_id") == run_id:
            return True
    return False


def format_run_candidate(rec: Dict[str, Any]) -> str:
    run_id = rec.get("run_id") or "(legacy:no run_id)"
    lens = rec.get("lens", "?")
    ts = rec.get("ts", "?")
    verdict = rec.get("verdict", "?")
    session = rec.get("session") or ",".join(rec.get("session_ids") or []) or "?"
    return f"{run_id}\tlens={lens}\tts={ts}\tverdict={verdict}\tsession={session}"


def resolve_lens_run_for_close(
    log_path: Path,
    *,
    deliverable: Optional[str] = None,
    run_id: Optional[str] = None,
    lens: Optional[str] = None,
    session: Optional[str] = None,
) -> Dict[str, Any]:
    """Pick the lens_run a human_review closes. Refuse ambiguous deliverable-only."""
    if run_id:
        run = get_lens_run_by_id(log_path, run_id)
        if not run:
            raise ValueError(f"unknown lens_run_id {run_id!r}")
        if deliverable and run.get("deliverable") != deliverable:
            raise ValueError(
                f"lens_run_id {run_id!r} is for deliverable {run.get('deliverable')!r}, "
                f"not {deliverable!r}"
            )
        return run

    if not deliverable:
        raise ValueError("deliverable or --run-id required")

    runs = list_lens_runs_for_deliverable(log_path, deliverable)
    if not runs:
        raise ValueError(f"no lens_run for deliverable {deliverable!r}")

    if lens or session:
        filtered: List[Dict[str, Any]] = []
        for rec in runs:
            if lens and rec.get("lens") != lens:
                continue
            if session:
                ids = _lens_run_session_ids(rec)
                if session not in ids:
                    continue
            filtered.append(rec)
        runs = filtered
        if not runs:
            raise ValueError("no lens_run matches --lens / --session filter")

    if len(runs) == 1:
        return runs[0]

    raise AmbiguousCloseError(
        f"deliverable {deliverable!r} has {len(runs)} lens_run candidates; "
        "pass --run-id (see: python -m lens_lib runs list --deliverable …)",
        runs,
    )


def validate_lens_skip_shape(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for k in ("ts", "event", "deliverable"):
        if k not in record:
            errors.append(f"missing {k}")
    if record.get("event") != "lens_skip":
        errors.append("event must be lens_skip")
    if not str(record.get("deliverable") or "").strip():
        errors.append("deliverable must be non-empty")
    allowed = {"ts", "event", "deliverable", "session", "session_ids", "reason", "host"}
    extra = set(record.keys()) - allowed
    if extra:
        errors.append(f"unknown keys: {sorted(extra)}")
    return errors


def validate_lens_run_shape(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = [
        "ts",
        "event",
        "lens",
        "deliverable",
        "rounds",
        "verdict",
        "findings",
        "escalations",
    ]
    for k in required:
        if k not in record:
            errors.append(f"missing {k}")
    if record.get("event") != "lens_run":
        errors.append("event must be lens_run")
    if record.get("verdict") not in VALID_VERDICTS:
        errors.append("verdict must be pass|escalated|held")
    run_id = record.get("run_id")
    if run_id is not None and not RUN_ID_RE.match(str(run_id)):
        errors.append("bad run_id")
    allowed = {
        "ts",
        "event",
        "run_id",
        "lens",
        "deliverable",
        "rounds",
        "verdict",
        "host",
        "session",
        "session_ids",
        "findings",
        "escalations",
    }
    extra = set(record.keys()) - allowed
    if extra:
        errors.append(f"unknown keys: {sorted(extra)}")
    findings = record.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be array")
    else:
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                errors.append(f"findings[{i}] not object")
                continue
            for k in ("round", "check", "target", "severity", "reaction"):
                if k not in f:
                    errors.append(f"findings[{i}] missing {k}")
            if f.get("reaction") not in VALID_REACTIONS:
                errors.append(
                    f"findings[{i}] reaction must be one of: "
                    + "|".join(sorted(VALID_REACTIONS))
                )
            extra = set(f.keys()) - FINDING_KEYS
            if extra:
                errors.append(f"findings[{i}] unknown keys: {sorted(extra)}")
            if f.get("check") and not CHECK_SLUG_RE.match(str(f["check"])):
                errors.append(f"findings[{i}] bad check slug")
            if f.get("class") is not None and not CHECK_SLUG_RE.match(str(f["class"])):
                errors.append(f"findings[{i}] bad class label")
    return errors
