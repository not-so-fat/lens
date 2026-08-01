"""Path matching for watch_globs (§7.4)."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterable, List

from .util import claude_home, system_temp_dir


def is_excluded(path: Path) -> bool:
    """Paths under ~/.claude/ and the system temp directory never match."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    claude = claude_home()
    tmp = system_temp_dir()
    try:
        resolved.relative_to(claude)
        return True
    except ValueError:
        pass
    try:
        resolved.relative_to(tmp)
        return True
    except ValueError:
        pass
    return False


def matches_glob(path_str: str, pattern: str) -> bool:
    """fnmatch against full string; support **/basename patterns."""
    if fnmatch.fnmatch(path_str, pattern):
        return True
    # Normalize separators for matching
    norm = path_str.replace("\\", "/")
    if fnmatch.fnmatch(norm, pattern):
        return True
    if pattern.startswith("**/"):
        rest = pattern[3:]
        if fnmatch.fnmatch(os.path.basename(norm), rest):
            return True
        if fnmatch.fnmatch(norm, rest):
            return True
        # match any path suffix
        if fnmatch.fnmatch(norm, "*/" + rest) or fnmatch.fnmatch(norm, "*/*/" + rest):
            return True
        parts = norm.split("/")
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if fnmatch.fnmatch(suffix, rest):
                return True
    return False


def path_matches_watch(path: str, watch_globs: Iterable[str], cwd: str) -> bool:
    abs_path = os.path.abspath(os.path.expanduser(path))
    p = Path(abs_path)
    if is_excluded(p):
        return False
    try:
        rel = os.path.relpath(abs_path, cwd)
    except ValueError:
        rel = abs_path
    for pat in watch_globs:
        if matches_glob(abs_path, pat) or matches_glob(rel, pat):
            return True
    return False


def filter_watched(paths: List[str], watch_globs: Iterable[str], cwd: str) -> List[str]:
    return [p for p in paths if path_matches_watch(p, watch_globs, cwd)]
