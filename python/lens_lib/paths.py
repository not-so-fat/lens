"""Path matching for watch_globs (§7.4)."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Tuple

from .util import claude_home, codex_home, system_temp_dir


def is_excluded(path: Path) -> bool:
    """Paths under ~/.claude/, ~/.codex/, and the system temp dir never match."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for base in (claude_home(), codex_home(), system_temp_dir()):
        try:
            resolved.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a glob with `**` / `*` to a regex (POSIX separators)."""
    i = 0
    out = ["^"]
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def matches_glob(path_str: str, pattern: str) -> bool:
    """Match path against a glob; `**` crosses directories."""
    norm = path_str.replace("\\", "/")
    if fnmatch.fnmatch(norm, pattern):
        return True
    try:
        if PurePosixPath(norm).match(pattern):
            return True
    except (ValueError, OSError):
        pass
    try:
        if _glob_to_regex(pattern).match(norm):
            return True
    except re.error:
        pass
    if pattern.startswith("**/"):
        rest = pattern[3:]
        if fnmatch.fnmatch(os.path.basename(norm), rest):
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


def filter_watched(
    paths: List[str], watch_globs: Iterable[str], cwd: str
) -> Tuple[List[str], int]:
    """Return (watched_paths, excluded_count) where excluded = temp/~/.claude drops."""
    watched: List[str] = []
    excluded = 0
    globs = list(watch_globs)
    for path in paths:
        abs_path = os.path.abspath(os.path.expanduser(path))
        if is_excluded(Path(abs_path)):
            excluded += 1
            continue
        if path_matches_watch(path, globs, cwd):
            watched.append(path)
    return watched, excluded
