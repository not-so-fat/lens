#!/usr/bin/env python3
"""Cursor stop hook entry — followup_message for a single forced continuation (F5.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.check import run_check  # noqa: E402
from lens_lib.util import CURSOR_UNLOCK_HINT  # noqa: E402


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

    result = run_check(
        host="cursor",
        transcript_path=transcript,
        session_id=session,
        session_ids=session_ids,
        cwd=cwd,
    )

    out = {}
    if result.blocked and result.message:
        out["followup_message"] = f"{result.message} {CURSOR_UNLOCK_HINT}"

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
