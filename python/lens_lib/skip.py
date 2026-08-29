"""Append lens_skip records (/lens-skip).

A lens_skip is the loop's second exit: the owner deliberately held a review for
a deliverable. It is recorded (never silent) and satisfies the Stop-hook gate
for that session, exactly the way a lens_run does.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from .check import read_arm_ts
from .config import resolve_config
from .log import (
    append_record,
    has_lens_skip_for_sessions,
    latest_gate_ts,
    latest_lens_skip_for_sessions,
    latest_lens_skip_ts,
)
from .transcript import load_sidechannel_writes
from .util import (
    conversation_workspace_writes_path,
    session_writes_path,
    utc_now_iso,
)


def _pending_write_batch_start(
    log_path,
    session: str,
    *,
    workspace_root: Optional[str] = None,
) -> Optional[str]:
    """Earliest side-channel write ts strictly after the last gate satisfaction."""
    gate_ts = latest_gate_ts(log_path, [session])
    side_paths = [str(session_writes_path(session))]
    root = workspace_root or os.getcwd()
    try:
        side_paths.append(str(conversation_workspace_writes_path(root, session)))
    except OSError:
        pass
    earliest: Optional[str] = None
    for sc in side_paths:
        _, first = load_sidechannel_writes(sc, after_ts=gate_ts)
        if first and (earliest is None or first < earliest):
            earliest = first
    return earliest


def skip_deliverable(
    deliverable: str,
    *,
    session: Optional[str] = None,
    reason: Optional[str] = None,
    host: Optional[str] = None,
    workspace_root: Optional[str] = None,
) -> Tuple[dict, str, bool]:
    """
    Append a lens_skip unless one already satisfies the pending batch.

    Returns (record, log_path, appended).
    """
    if not deliverable or not deliverable.strip():
        raise ValueError("lens_skip requires a non-empty deliverable key")
    cfg = resolve_config()
    if session and session != "unknown":
        gate_ts = latest_gate_ts(cfg.log_path, [session])
        skip_ts = latest_lens_skip_ts(cfg.log_path, [session])
        pending = _pending_write_batch_start(
            cfg.log_path, session, workspace_root=workspace_root
        )
        if pending is None:
            if skip_ts and gate_ts == skip_ts:
                existing = latest_lens_skip_for_sessions(
                    cfg.log_path, [session], since_iso=skip_ts
                )
                if existing is not None:
                    return existing, str(cfg.log_path), False
            arm_ts = read_arm_ts(session)
            if arm_ts and has_lens_skip_for_sessions(
                cfg.log_path, [session], since_iso=arm_ts
            ):
                existing = latest_lens_skip_for_sessions(
                    cfg.log_path, [session], since_iso=arm_ts
                )
                if existing is not None:
                    return existing, str(cfg.log_path), False
        elif has_lens_skip_for_sessions(
            cfg.log_path, [session], since_iso=pending
        ):
            existing = latest_lens_skip_for_sessions(
                cfg.log_path, [session], since_iso=pending
            )
            if existing is not None:
                return existing, str(cfg.log_path), False

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
    return record, str(path), True
