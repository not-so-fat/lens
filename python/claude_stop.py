#!/usr/bin/env python3
"""Claude Code Stop hook entry — exit 2 to block (F3)."""

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

    transcript = payload.get("transcript_path") or payload.get("transcriptPath")
    session = payload.get("session_id") or payload.get("sessionId")
    cwd = payload.get("cwd")

    result = run_check(
        host="claude-code",
        transcript_path=transcript,
        session_id=session,
        cwd=cwd,
    )

    if result.message and not result.blocked:
        # enforce=false warning
        print(result.message, file=sys.stderr)

    if result.blocked:
        # Claude Code: exit 2 + stderr message blocks stop
        print(result.message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
