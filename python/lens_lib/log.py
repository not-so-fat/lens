"""Append-only JSONL run log at config log_path."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .util import utc_now_iso

CHECK_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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


def has_lens_run_since(log_path: Path, since_iso: Optional[str]) -> bool:
    """
    True if any lens_run has ts >= since_iso.

    Fail closed when since_iso is None — never treat an unbounded window as
    satisfied by a historical run (Cursor thin stop payloads).
    """
    if since_iso is None:
        return False
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run":
            continue
        ts = rec.get("ts") or ""
        if ts >= since_iso:
            return True
    return False


def has_lens_run_for_sessions(
    log_path: Path, session_ids: Sequence[str]
) -> bool:
    """True if a lens_run is tagged with any of the current conversation/session ids."""
    wanted = {str(s) for s in session_ids if s and s != "unknown"}
    if not wanted:
        return False
    for rec in iter_records(log_path):
        if rec.get("event") != "lens_run":
            continue
        rec_ids = set()
        if rec.get("session"):
            rec_ids.add(str(rec["session"]))
        for sid in rec.get("session_ids") or []:
            if sid:
                rec_ids.add(str(sid))
        if rec_ids & wanted:
            return True
    return False


def deliverable_has_lens_run(log_path: Path, deliverable: str) -> bool:
    for rec in iter_records(log_path):
        if rec.get("event") == "lens_run" and rec.get("deliverable") == deliverable:
            return True
    return False


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
            if f.get("check") and not CHECK_SLUG_RE.match(str(f["check"])):
                errors.append(f"findings[{i}] bad check slug")
    return errors
