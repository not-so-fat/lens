"""Parse session transcripts for written file paths and first-event time."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from .log import parse_iso_ts

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
                continue  # skip junk banners; do not fail the whole transcript
            ts = obj.get("timestamp") or obj.get("ts")
            if isinstance(ts, str) and ts:
                return ts
    return None


def _paths_from_tool_input(inp: dict, out: Set[str]) -> None:
    for key in ("file_path", "filePath", "path", "notebook_path"):
        val = inp.get(key)
        if isinstance(val, str) and val:
            out.add(val)


def _tool_name(obj: dict) -> str:
    """Return a string tool id, or '' if missing/non-string (e.g. JSON Schema props)."""
    for key in ("name", "toolName"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _walk(obj, out: Set[str]) -> None:
    if isinstance(obj, dict):
        name = _tool_name(obj)
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


def extensions_from_watch_globs(watch_globs: Iterable[str]) -> List[str]:
    """Derive file extensions from globs like `**/*.md` → `md`."""
    exts: List[str] = []
    for pat in watch_globs:
        m = re.search(r"\.([A-Za-z0-9]+)\)?$", pat.replace("**/", ""))
        if not m:
            m = re.search(r"\.([A-Za-z0-9]+)$", pat)
        if m:
            ext = m.group(1).lower()
            if ext not in exts:
                exts.append(ext)
    return exts


def written_paths_from_transcript(
    transcript_path: str,
    *,
    watch_globs: Optional[Iterable[str]] = None,
) -> List[str]:
    path = Path(transcript_path)
    if not path.is_file():
        return []
    exts = extensions_from_watch_globs(watch_globs or [])
    if not exts:
        exts = ["md", "html", "pptx"]
    ext_alt = "|".join(re.escape(e) for e in exts)
    fallback_re = re.compile(rf"(/[^\s\"']+\.(?:{ext_alt}))")
    found: Set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                for m in fallback_re.finditer(line):
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


def load_sidechannel_writes(
    writes_file: str,
    *,
    after_ts: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """
    Load paths from a side-channel file.

    If after_ts is set, keep only lines with ts strictly after that instant
    (unstamped legacy lines are dropped when filtering).
    Returns (paths, earliest_kept_ts).
    """
    path = Path(writes_file)
    if not path.is_file():
        return [], None
    after = parse_iso_ts(after_ts) if after_ts else None
    out: List[str] = []
    earliest: Optional[str] = None
    earliest_dt = None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ts, file_path = parse_sidechannel_line(ln)
        if not file_path:
            continue
        if after is not None:
            if not ts:
                continue
            dt = parse_iso_ts(ts)
            if dt is None or dt <= after:
                continue
        out.append(file_path)
        if ts:
            dt = parse_iso_ts(ts)
            if dt is not None and (earliest_dt is None or dt < earliest_dt):
                earliest_dt = dt
                earliest = ts
    return out, earliest


def sidechannel_first_ts(writes_file: str) -> Optional[str]:
    """Earliest stamped write time in a side-channel file."""
    _, earliest = load_sidechannel_writes(writes_file)
    return earliest


def prune_sidechannel_file(writes_file: str, *, after_ts: Optional[str]) -> None:
    """Rewrite a side-channel file keeping only lines strictly after after_ts."""
    path = Path(writes_file)
    if not path.is_file():
        return
    if after_ts is None:
        path.write_text("", encoding="utf-8")
        return
    after = parse_iso_ts(after_ts)
    if after is None:
        return
    kept: List[str] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ts, file_path = parse_sidechannel_line(ln)
        if not file_path:
            continue
        if not ts:
            continue
        dt = parse_iso_ts(ts)
        if dt is not None and dt > after:
            kept.append(f"{ts}\t{file_path}")
    path.write_text(("\n".join(kept) + ("\n" if kept else "")), encoding="utf-8")


_AGENT_TOOL_NAMES = {"Agent", "Task", "agent", "task"}


def _is_lens_subagent_type(value: object) -> bool:
    """True for host subagent ids that invoke the lens runner (e.g. ``lens:lens``)."""
    if not isinstance(value, str):
        return False
    # Plugin form is often "lens:lens"; bare "lens" also appears.
    parts = [p for p in value.lower().replace("/", ":").split(":") if p]
    return "lens" in parts


def _obj_launches_lens_agent(obj: object) -> bool:
    if isinstance(obj, dict):
        name = _tool_name(obj)
        if name in _AGENT_TOOL_NAMES or (
            obj.get("type") == "tool_use" and name in _AGENT_TOOL_NAMES
        ):
            inp = obj.get("input") or obj.get("arguments") or {}
            if isinstance(inp, dict) and _is_lens_subagent_type(
                inp.get("subagent_type") or inp.get("subagentType")
            ):
                return True
        return any(_obj_launches_lens_agent(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_obj_launches_lens_agent(v) for v in obj)
    return False


def latest_lens_agent_launch_ts(transcript_path: str) -> Optional[str]:
    """Latest transcript timestamp of an Agent/Task tool_use that starts the lens runner.

    Used so Stop can treat a *background* lens review as fulfilling the obligation
    (``skip_reason=review_in_flight``) instead of force-continuing the parent.
    Claude returns ``Async agent launched`` immediately; launch detection is the
    signal we have until a ``lens_run``/``lens_skip`` lands (or the crash backstop
    in ``run_check`` ends the in-flight pass).
    """
    path = Path(transcript_path)
    if not path.is_file():
        return None
    latest_raw: Optional[str] = None
    latest_dt = None
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or not _obj_launches_lens_agent(obj):
                continue
            raw = obj.get("timestamp") or obj.get("ts")
            if not isinstance(raw, str) or not raw:
                continue
            dt = parse_iso_ts(raw)
            if dt is None:
                continue
            if latest_dt is None or dt >= latest_dt:
                latest_dt = dt
                latest_raw = raw
    return latest_raw


def gather_writes(
    transcript_path: Optional[str],
    sidechannel_path: Optional[str] = None,
    sidechannel_paths: Optional[List[str]] = None,
    *,
    watch_globs: Optional[Iterable[str]] = None,
    after_ts: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Return (written_paths, first_event_ts)."""
    paths: Set[str] = set()
    # F3.1: transcript first-event time is the session window when present.
    first_ts: Optional[str] = (
        first_event_ts(transcript_path) if transcript_path else None
    )
    if transcript_path:
        paths.update(
            written_paths_from_transcript(transcript_path, watch_globs=watch_globs)
        )
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
        # Cursor: only count writes after the last session gate satisfaction.
        sc_paths, sc_first = load_sidechannel_writes(sc, after_ts=after_ts)
        paths.update(sc_paths)
        if sc_first and (side_first is None or sc_first < side_first):
            side_first = sc_first
    # Cursor thin stop: no transcript — bound the gate by earliest remaining write.
    if first_ts is None:
        first_ts = side_first
    return sorted(paths), first_ts
