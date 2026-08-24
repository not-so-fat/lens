"""Append human_review records (/lens-close)."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .config import resolve_config
from .corrections import capture_from_human_review
from .log import append_record, deliverable_has_lens_run
from .util import utc_now_iso

TAGGED_RE = re.compile(r"^([a-z0-9]+(?:-[a-z0-9]+)*)\s*:\s*(.+)$")


def parse_tagged(items: List[str]) -> List[dict]:
    out = []
    for item in items:
        m = TAGGED_RE.match(item.strip())
        if not m:
            raise ValueError(f"expected check:note, got: {item!r}")
        out.append({"check": m.group(1), "note": m.group(2)})
    return out


def close_deliverable(
    deliverable: str,
    corrections: int,
    misses: Optional[List[str]] = None,
    noise: Optional[List[str]] = None,
) -> Tuple[dict, str, List[dict]]:
    cfg = resolve_config()
    if not deliverable_has_lens_run(cfg.log_path, deliverable):
        raise ValueError(
            f"no lens_run for deliverable {deliverable!r}; refuse human_review"
        )
    record: dict = {
        "ts": utc_now_iso(),
        "event": "human_review",
        "deliverable": deliverable,
        "corrections": int(corrections),
    }
    if misses:
        record["misses"] = parse_tagged(misses)
    if noise:
        record["noise"] = parse_tagged(noise)
    path = append_record(cfg.log_path, record)
    signals = []
    if record.get("misses") or record.get("noise"):
        signals = capture_from_human_review(
            deliverable=deliverable,
            misses=record.get("misses"),
            noise=record.get("noise"),
            log_path=cfg.log_path,
        )
    return record, str(path), signals
