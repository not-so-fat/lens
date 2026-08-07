#!/usr/bin/env python3
"""Codex Stop hook entry — block via {"decision": "block"} (F6, mirrors F3).

Codex writes go through a PostToolUse side-channel (see codex_post_tool_use.py),
not the transcript, so — like Cursor — this passes no transcript_path and lets
run_check gate on the side-channel writes. A block is returned as
``{"decision": "block", "reason": ...}`` (Codex re-prompts to continue); an
enforce=false / arm warning goes to stderr without blocking.
"""

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

    session = payload.get("session_id") or payload.get("sessionId")
    session_ids = []
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        val = payload.get(key)
        if val and str(val) not in session_ids:
            session_ids.append(str(val))
    cwd = payload.get("cwd")

    # No transcript_path: Codex writes are side-channel-recorded (apply_patch is
    # not parseable from the transcript). This selects the side-channel gate path.
    result = run_check(
        host="codex",
        transcript_path=None,
        session_id=session,
        session_ids=session_ids or None,
        cwd=cwd,
    )

    out = {}
    if result.blocked and result.message:
        out = {"decision": "block", "reason": result.message}
    elif result.message and not result.blocked:
        # enforce=false or warn-first arm notice — surface without blocking.
        print(result.message, file=sys.stderr)

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
