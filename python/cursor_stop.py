#!/usr/bin/env python3
"""Cursor stop hook entry — followup_message for bounded continuation (F5.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.check import run_check  # noqa: E402
from lens_lib.config import resolve_config  # noqa: E402
from lens_lib.log import append_record  # noqa: E402
from lens_lib.util import (  # noqa: E402
    CURSOR_LOOP_LIMIT_DEFAULT,
    CURSOR_UNLOCK_HINT,
    utc_now_iso,
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    transcript = (
        payload.get("transcript_path")
        or payload.get("transcriptPath")
        or None
    )
    # Prefer conversation_id first (I-3 analysis / primary key).
    session_ids = []
    for key in ("conversation_id", "conversationId", "session_id", "sessionId"):
        val = payload.get(key)
        if val and str(val) not in session_ids:
            session_ids.append(str(val))
    session = session_ids[0] if session_ids else None
    roots = payload.get("workspace_roots") or payload.get("workspaceRoots") or []
    cwd = roots[0] if roots else payload.get("cwd")

    loop_count = payload.get("loop_count")
    if not isinstance(loop_count, int):
        loop_count = 0
    loop_limit = payload.get("loop_limit")
    if not isinstance(loop_limit, int):
        loop_limit = CURSOR_LOOP_LIMIT_DEFAULT

    result = run_check(
        host="cursor",
        transcript_path=transcript,
        session_id=session,
        session_ids=session_ids,
        cwd=cwd,
    )

    out = {}
    if result.blocked and result.message:
        if loop_count >= loop_limit:
            try:
                cfg = resolve_config()
                append_record(
                    cfg.log_path,
                    {
                        "ts": utc_now_iso(),
                        "event": "hook_limit_exhausted",
                        "session": result.session,
                        "session_ids": session_ids,
                        "loop_count": loop_count,
                        "loop_limit": loop_limit,
                        "host": "cursor",
                        "watched_paths": result.watched_paths[:8],
                    },
                )
            except Exception:
                pass
            print(
                f"Lens: loop_limit ({loop_limit}) exhausted; enforcement no longer forced. "
                f"{CURSOR_UNLOCK_HINT}",
                file=sys.stderr,
            )
        elif loop_count >= max(0, loop_limit - 1):
            out["followup_message"] = (
                f"{result.message} "
                f"LAST FORCED FOLLOW-UP (loop_count={loop_count}, limit={loop_limit}). "
                f"{CURSOR_UNLOCK_HINT}"
            )
        else:
            out["followup_message"] = f"{result.message} {CURSOR_UNLOCK_HINT}"

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
