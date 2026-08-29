"""Append human_review records (/lens-close)."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .config import resolve_config
from .corrections import capture_from_human_review
from .log import (
    AmbiguousCloseError,
    append_record,
    format_run_candidate,
    human_review_exists_for_run,
    resolve_lens_run_for_close,
)
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
    deliverable: Optional[str],
    corrections: int,
    *,
    run_id: Optional[str] = None,
    lens: Optional[str] = None,
    session: Optional[str] = None,
    misses: Optional[List[str]] = None,
    noise: Optional[List[str]] = None,
) -> Tuple[dict, str, List[dict]]:
    cfg = resolve_config()
    try:
        run = resolve_lens_run_for_close(
            cfg.log_path,
            deliverable=deliverable,
            run_id=run_id,
            lens=lens,
            session=session,
        )
    except AmbiguousCloseError as e:
        lines = [str(e), "candidates:"]
        lines.extend(format_run_candidate(c) for c in e.candidates)
        raise ValueError("\n".join(lines)) from e

    deliverable_key = str(run["deliverable"])
    attached_run_id = run.get("run_id")
    if attached_run_id and human_review_exists_for_run(cfg.log_path, str(attached_run_id)):
        raise ValueError(
            f"human_review already recorded for lens_run_id {attached_run_id!r}"
        )

    record: dict = {
        "ts": utc_now_iso(),
        "event": "human_review",
        "deliverable": deliverable_key,
        "corrections": int(corrections),
    }
    if attached_run_id:
        record["lens_run_id"] = attached_run_id
    if run.get("ts"):
        record["lens_run_ts"] = run["ts"]
    if misses:
        record["misses"] = parse_tagged(misses)
    if noise:
        record["noise"] = parse_tagged(noise)
    path = append_record(cfg.log_path, record)
    signals = []
    if record.get("misses") or record.get("noise"):
        signals = capture_from_human_review(
            run=run,
            misses=record.get("misses"),
            noise=record.get("noise"),
        )
    return record, str(path), signals
