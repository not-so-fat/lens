"""Append-only JSONL run log at config log_path."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .util import utc_now_iso

CHECK_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FINDING_KEYS = frozenset(
    {"round", "check", "target", "severity", "reaction", "note", "class"}
)


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
    Both pass and escalated terminal lens_run records satisfy the gate.
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
    """True if a lens_run satisfies this session's gate (pass or escalated)."""
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


def latest_lens_run_ts(
    log_path: Path, session_ids: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Latest lens_run ts, optionally restricted to matching session ids."""
    wanted = None
    if session_ids is not None:
        wanted = {str(s) for s in session_ids if s and s != "unknown"}
        if not wanted:
            return None
    latest: Optional[datetime] = None
    latest_raw: Optional[str] = None
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run":
            continue
        if wanted is not None:
            rec_ids = set()
            if rec.get("session"):
                rec_ids.add(str(rec["session"]))
            for sid in rec.get("session_ids") or []:
                if sid:
                    rec_ids.add(str(sid))
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
    latest: Optional[datetime] = None
    latest_rec: Optional[Dict[str, Any]] = None
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run" or rec.get("deliverable") != deliverable:
            continue
        ts = parse_iso_ts(str(rec.get("ts") or ""))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
            latest_rec = rec
    return latest_rec


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
    if record.get("verdict") not in ("pass", "escalated"):
        errors.append("verdict must be pass|escalated")
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
            extra = set(f.keys()) - FINDING_KEYS
            if extra:
                errors.append(f"findings[{i}] unknown keys: {sorted(extra)}")
            if f.get("check") and not CHECK_SLUG_RE.match(str(f["check"])):
                errors.append(f"findings[{i}] bad check slug")
            if f.get("class") is not None and not CHECK_SLUG_RE.match(str(f["class"])):
                errors.append(f"findings[{i}] bad class label")
    return errors
