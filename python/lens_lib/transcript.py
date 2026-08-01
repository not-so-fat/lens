"""Parse session transcripts for written file paths and first-event time."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

WRITE_TOOLS = {
    "Write",
    "Edit",
    "NotebookEdit",
    "write",
    "edit",
    "search_replace",
    "StrReplace",
    "WriteFile",
    "EditNotebook",
}


def session_id_from_transcript(transcript_path: str, fallback: str = "") -> str:
    name = Path(transcript_path).stem
    return name or fallback or "unknown"


def first_event_ts(transcript_path: str) -> Optional[str]:
    path = Path(transcript_path)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return None
            ts = obj.get("timestamp") or obj.get("ts")
            if isinstance(ts, str) and ts:
                return ts
    return None


def _paths_from_tool_input(inp: dict, out: Set[str]) -> None:
    for key in ("file_path", "filePath", "path", "notebook_path"):
        val = inp.get(key)
        if isinstance(val, str) and val:
            out.add(val)


def _walk(obj, out: Set[str]) -> None:
    if isinstance(obj, dict):
        name = obj.get("name") or obj.get("toolName") or ""
        if name in WRITE_TOOLS:
            inp = obj.get("input") or obj.get("arguments") or {}
            if isinstance(inp, dict):
                _paths_from_tool_input(inp, out)
        if obj.get("type") == "tool_use" and name in WRITE_TOOLS:
            inp = obj.get("input") or {}
            if isinstance(inp, dict):
                _paths_from_tool_input(inp, out)
        if isinstance(obj.get("file_path"), str) and obj.get("hook_event_name") in (
            "afterFileEdit",
            "after_file_edit",
        ):
            out.add(obj["file_path"])
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, out)


def written_paths_from_transcript(transcript_path: str) -> List[str]:
    path = Path(transcript_path)
    if not path.is_file():
        return []
    found: Set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                for m in re.finditer(r"(/[^\s\"']+\.(?:md|html|pptx))", line):
                    found.add(m.group(1))
                continue
            _walk(obj, found)
    return sorted(found)


def parse_sidechannel_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a side-channel line.

    New format: `<ISO-Z>\\t<path>`. Legacy: bare path (no timestamp).
    Returns (ts_or_none, path_or_none).
    """
    line = line.strip()
    if not line:
        return None, None
    if "\t" in line:
        ts, _, path = line.partition("\t")
        ts = ts.strip()
        path = path.strip()
        if path:
            return (ts or None), path
        return None, None
    return None, line


def load_sidechannel_writes(writes_file: str) -> List[str]:
    path = Path(writes_file)
    if not path.is_file():
        return []
    out: List[str] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        _, file_path = parse_sidechannel_line(ln)
        if file_path:
            out.append(file_path)
    return out


def sidechannel_first_ts(writes_file: str) -> Optional[str]:
    """Earliest stamped write time in a side-channel file (ISO-Z string min)."""
    path = Path(writes_file)
    if not path.is_file():
        return None
    earliest: Optional[str] = None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ts, file_path = parse_sidechannel_line(ln)
        if not file_path or not ts:
            continue
        if earliest is None or ts < earliest:
            earliest = ts
    return earliest


def gather_writes(
    transcript_path: Optional[str],
    sidechannel_path: Optional[str] = None,
    sidechannel_paths: Optional[List[str]] = None,
) -> Tuple[List[str], Optional[str]]:
    """Return (written_paths, first_event_ts)."""
    paths: Set[str] = set()
    # F3.1: transcript first-event time is the session window when present.
    first_ts: Optional[str] = (
        first_event_ts(transcript_path) if transcript_path else None
    )
    if transcript_path:
        paths.update(written_paths_from_transcript(transcript_path))
    extras: List[str] = []
    if sidechannel_paths:
        extras.extend(sidechannel_paths)
    if sidechannel_path:
        extras.append(sidechannel_path)
    seen_files: Set[str] = set()
    side_first: Optional[str] = None
    for sc in extras:
        if not sc or sc in seen_files:
            continue
        seen_files.add(sc)
        paths.update(load_sidechannel_writes(sc))
        sc_ts = sidechannel_first_ts(sc)
        if sc_ts and (side_first is None or sc_ts < side_first):
            side_first = sc_ts
    # Cursor thin stop: no transcript — bound the gate by earliest stamped write.
    if first_ts is None:
        first_ts = side_first
    return sorted(paths), first_ts
