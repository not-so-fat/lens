#!/usr/bin/env python3
"""Cursor afterFileEdit — record written path for stop-hook watch detection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.check import record_sidechannel_write  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    file_path = payload.get("file_path") or payload.get("filePath")
    session = (
        payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("conversation_id")
        or "unknown"
    )
    if file_path:
        try:
            record_sidechannel_write(str(session), str(file_path))
        except OSError:
            pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
