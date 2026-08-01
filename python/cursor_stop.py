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
    session = (
        payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("conversation_id")
    )
    roots = payload.get("workspace_roots") or []
    cwd = roots[0] if roots else None

    result = run_check(
        host="cursor",
        transcript_path=transcript,
        session_id=session,
        cwd=cwd,
    )

    out = {}
    if result.blocked and result.message:
        # Bounded continuation (loop_limit on the hook entry)
        out["followup_message"] = result.message
    # enforce=false: do not followup (would loop); hook_check is already logged

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
