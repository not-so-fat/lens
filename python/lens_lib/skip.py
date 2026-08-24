"""Append lens_skip records (/lens-skip).

A lens_skip is the loop's second exit: the owner deliberately held a review for
a deliverable. It is recorded (never silent) and satisfies the Stop-hook gate
for that session, exactly the way a lens_run does.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .config import resolve_config
from .log import append_record
from .util import utc_now_iso


def skip_deliverable(
    deliverable: str,
    *,
    session: Optional[str] = None,
    reason: Optional[str] = None,
    host: Optional[str] = None,
) -> Tuple[dict, str]:
    if not deliverable or not deliverable.strip():
        raise ValueError("lens_skip requires a non-empty deliverable key")
    cfg = resolve_config()
    record: dict = {
        "ts": utc_now_iso(),
        "event": "lens_skip",
        "deliverable": deliverable,
    }
    if session:
        record["session"] = session
    if reason:
        record["reason"] = reason
    if host:
        record["host"] = host
    path = append_record(cfg.log_path, record)
    return record, str(path)
