"""Extract written file paths from a Codex PostToolUse payload.

Codex edits files through ``apply_patch`` (often wrapped in a ``shell`` /
``local_shell`` tool call), not through a ``Write``/``Edit`` tool with a clean
``file_path`` field. So — unlike the Claude transcript path — the written paths
live inside an ``apply_patch`` envelope:

    *** Begin Patch
    *** Update File: path/to/file.md
    *** Add File: path/to/new.md
    *** Delete File: path/to/old.md
    *** Move to: path/to/renamed.md
    *** End Patch

This module pulls those paths out of whatever shape ``tool_input`` carries
(string, ``{"command": [...]}``, ``{"input": "..."}``, nested), plus any explicit
``file_path`` / ``path`` key. It is deliberately conservative: it keys off the
``apply_patch`` markers and explicit path fields, never off arbitrary shell text,
so a ``cat``/``grep`` mentioning a filename does not count as a write.
"""

from __future__ import annotations

import re
from typing import Any, List

# `*** Update File: <path>` / Add / Delete, and the `*** Move to: <path>` rename
# destination. Path runs to end of line; trailing whitespace stripped by caller.
_PATCH_FILE_RE = re.compile(
    r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+?)\s*$", re.MULTILINE
)
_PATCH_MOVE_RE = re.compile(r"^\*\*\*\s+Move\s+to:\s*(.+?)\s*$", re.MULTILINE)

_PATH_KEYS = ("file_path", "filePath", "path", "notebook_path")


def _collect_strings(obj: Any, out: List[str]) -> None:
    """Recursively gather every string value in a tool_input structure."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, out)


def _explicit_path_fields(obj: Any, out: List[str]) -> None:
    """Pull values of explicit path keys (a direct file-edit tool, if Codex uses one)."""
    if isinstance(obj, dict):
        for key in _PATH_KEYS:
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
        for v in obj.values():
            _explicit_path_fields(v, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _explicit_path_fields(item, out)


def extract_codex_write_paths(tool_name: Any, tool_input: Any) -> List[str]:
    """Return the file paths a Codex tool call wrote, de-duplicated in order.

    Recognizes apply_patch envelopes (in any nesting) and explicit path fields.
    Returns [] for read-only or unrecognized calls.
    """
    found: List[str] = []

    strings: List[str] = []
    _collect_strings(tool_input, strings)
    blob = "\n".join(strings)
    if "*** " in blob and ("Begin Patch" in blob or "File:" in blob or "Move to:" in blob):
        for m in _PATCH_FILE_RE.finditer(blob):
            found.append(m.group(1).strip())
        for m in _PATCH_MOVE_RE.finditer(blob):
            found.append(m.group(1).strip())

    _explicit_path_fields(tool_input, found)

    seen = set()
    ordered: List[str] = []
    for p in found:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered
