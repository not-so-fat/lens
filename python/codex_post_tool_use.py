#!/usr/bin/env python3
"""Codex PostToolUse hook — record written paths for stop-hook enforcement.

Codex edits via ``apply_patch`` (no ``Write``/``Edit`` tool with a clean
``file_path``), so its Stop transcript can't be parsed for writes the way
Claude's can. Mirror the Cursor ``afterFileEdit`` side-channel instead: on every
tool call, pull the written paths out of the ``apply_patch`` envelope and record
them for the Stop hook to gather.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.check import record_sidechannel_write  # noqa: E402
from lens_lib.codex_writes import extract_codex_write_paths  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    tool_name = payload.get("tool_name") or payload.get("toolName")
    tool_input = (
        payload.get("tool_input")
        if payload.get("tool_input") is not None
        else payload.get("toolInput")
    )
    paths = extract_codex_write_paths(tool_name, tool_input)

    sessions = []
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        val = payload.get(key)
        if val and str(val) not in sessions:
            sessions.append(str(val))
    if not sessions:
        sessions = ["unknown"]

    workspace_root = payload.get("cwd") or payload.get("workspace_root")

    for file_path in paths:
        for session in sessions:
            try:
                record_sidechannel_write(
                    session, file_path, workspace_root=workspace_root
                )
            except OSError:
                pass

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
