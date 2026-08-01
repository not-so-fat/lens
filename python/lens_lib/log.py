"""Append-only JSONL run log."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .util import run_log_path, utc_now_iso

CHECK_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def ensure_log(vault_root: Path) -> Path:
    path = run_log_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def append_record(vault_root: Path, record: Dict[str, Any]) -> Path:
    """Append one complete JSONL line. Adds ts if missing."""
    if "ts" not in record:
        record = {**record, "ts": utc_now_iso()}
    path = ensure_log(vault_root)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def iter_records(vault_root: Path) -> Iterator[Dict[str, Any]]:
    path = run_log_path(vault_root)
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def has_lens_run_since(vault_root: Path, since_iso: Optional[str]) -> bool:
    """True if any lens_run has ts >= since_iso (string compare works for ISO-Z)."""
    for rec in iter_records(vault_root):
        if rec.get("event") != "lens_run":
            continue
        ts = rec.get("ts") or ""
        if since_iso is None or ts >= since_iso:
            return True
    return False


def deliverable_has_lens_run(vault_root: Path, deliverable: str) -> bool:
    for rec in iter_records(vault_root):
        if rec.get("event") == "lens_run" and rec.get("deliverable") == deliverable:
            return True
    return False


def validate_lens_run_shape(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = [
        "ts",
        "event",
        "lens",
        "area",
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
