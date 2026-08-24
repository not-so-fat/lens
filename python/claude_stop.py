#!/usr/bin/env python3
"""Claude Code Stop hook entry (F3).

Blocks via ``{"decision": "block", "reason": …}`` on stdout (exit 0) — the same
structured form Codex uses. This surfaces as enforcement *feedback*, not a
"Stop hook error": the hook is deciding to block, not failing.
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

    transcript = payload.get("transcript_path") or payload.get("transcriptPath")
    session = payload.get("session_id") or payload.get("sessionId")
    cwd = payload.get("cwd")

    result = run_check(
        host="claude-code",
        transcript_path=transcript,
        session_id=session,
        cwd=cwd,
    )

    out = {}
    if result.blocked and result.message:
        out = {"decision": "block", "reason": result.message}
    elif result.message and not result.blocked:
        # enforce=false warning — surface without blocking.
        print(result.message, file=sys.stderr)

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
