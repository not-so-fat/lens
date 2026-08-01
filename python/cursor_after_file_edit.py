#!/usr/bin/env python3
"""Cursor afterFileEdit — record written paths for stop-hook enforcement (F5.3)."""

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
        payload = {}

    file_path = payload.get("file_path") or payload.get("filePath")
    # Prefer conversation_id for analysis / primary keying (I-3).
    sessions = []
    for key in ("conversation_id", "conversationId", "session_id", "sessionId"):
        val = payload.get(key)
        if val and str(val) not in sessions:
            sessions.append(str(val))
    if not sessions:
        sessions = ["unknown"]

    roots = payload.get("workspace_roots") or payload.get("workspaceRoots") or []
    workspace_root = roots[0] if roots else payload.get("cwd")

    # I-1 host contract: workspace root should be present for reliable enforcement.
    if file_path and not workspace_root:
        print(
            "Lens afterFileEdit: no workspace_roots/cwd in payload; "
            "enforcement may miss writes if stop uses a different conversation id "
            "(see docs/ISSUES.md I-1).",
            file=sys.stderr,
        )

    if file_path:
        for session in sessions:
            try:
                record_sidechannel_write(
                    session, str(file_path), workspace_root=workspace_root
                )
            except OSError:
                pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
