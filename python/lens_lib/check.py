"""Shared Stop/stop hook check logic (F3 / F5.4)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import Config, ConfigError, resolve_config
from .log import append_record, has_lens_run_since
from .paths import filter_watched
from .transcript import gather_writes, session_id_from_transcript
from .util import INVOCATION_TEMPLATE, session_writes_path, utc_now_iso


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


def run_check(
    *,
    host: str,
    transcript_path: Optional[str] = None,
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
    config: Optional[Config] = None,
) -> CheckResult:
    """Evaluate whether this turn must invoke the lens runner before stopping."""
    started = time.perf_counter()
    cwd = cwd or os.getcwd()
    session = session_id or (
        session_id_from_transcript(transcript_path) if transcript_path else "unknown"
    )

    try:
        cfg = config or resolve_config()
    except ConfigError as e:
        duration_ms = (time.perf_counter() - started) * 1000
        # Cannot enforce without config — warn, do not block forever
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

    side = str(session_writes_path(session)) if session else None
    written, first_ts = gather_writes(transcript_path, side)
    watched = filter_watched(written, cfg.watch_globs, cwd)
    watched_writes = len(watched) > 0
    lens_run_found = False
    if watched_writes:
        lens_run_found = has_lens_run_since(cfg.vault_root, first_ts)

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

    duration_ms = (time.perf_counter() - started) * 1000

    # Always append hook_check when vault is known
    record: Dict[str, Any] = {
        "ts": utc_now_iso(),
        "event": "hook_check",
        "session": session,
        "watched_writes": watched_writes,
        "lens_run_found": lens_run_found,
        "blocked": should_block,
        "duration_ms": round(duration_ms, 3),
        "host": host,
    }
    try:
        append_record(cfg.vault_root, record)
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


def record_sidechannel_write(session: str, file_path: str) -> None:
    path = session_writes_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(file_path + "\n")
