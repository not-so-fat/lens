"""Path matching for watch_globs (§7.4)."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Tuple

from .util import claude_home, classic_temp_dirs, codex_home, system_temp_dir


def is_excluded(path: Path) -> bool:
    """Paths under ~/.claude/, ~/.codex/, and any temp dir never match.

    Temp covers `$TMPDIR` plus the classic `/tmp` / `/private/tmp` where agent
    harnesses stash session scratch (e.g. Claude Code's `.../scratchpad/*.md`).
    """
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for base in (claude_home(), codex_home(), system_temp_dir(), *classic_temp_dirs()):
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


# Paths that are never review deliverables — always ignored, regardless of config.
BUILTIN_IGNORE_GLOBS: Tuple[str, ...] = (
    "**/node_modules/**",
    "**/.git/**",
    "**/dist/**",
    "**/build/**",
    "**/__pycache__/**",
    "**/.lens/**",
)


def _read_ignore_file(path: Path) -> List[str]:
    pats: List[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return pats
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(line)
    return pats


def load_lensignore(cwd: str) -> List[str]:
    """Ignore globs from the nearest `.lensignore`, walking up from cwd.

    A repo-local `.lensignore` (gitignore-style: one glob per line, `#` comments)
    lets a repo exclude its own routine files (docs, notes, tests) from the write
    gate — committed once, it applies on every laptop.
    """
    try:
        start = Path(os.path.abspath(cwd))
    except (OSError, ValueError):
        return []
    for parent in [start, *start.parents]:
        candidate = parent / ".lensignore"
        if candidate.is_file():
            return _read_ignore_file(candidate)
    return []


def path_matches_ignore(path: str, ignore_globs: Iterable[str], cwd: str) -> bool:
    """True if path matches an ignore glob (abs, cwd-relative, or basename)."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    try:
        rel = os.path.relpath(abs_path, cwd)
    except ValueError:
        rel = abs_path
    base = os.path.basename(abs_path)
    for pat in ignore_globs:
        if matches_glob(abs_path, pat) or matches_glob(rel, pat):
            return True
        # gitignore-style: a slash-free pattern matches by basename anywhere.
        if "/" not in pat and matches_glob(base, pat):
            return True
    return False


def filter_watched(
    paths: List[str],
    watch_globs: Iterable[str],
    cwd: str,
    ignore_globs: Iterable[str] = (),
) -> Tuple[List[str], int]:
    """Return (watched_paths, excluded_count).

    Excluded = temp/~/.claude drops plus anything matching an ignore glob (routine
    files a repo/config marked as non-deliverable).
    """
    watched: List[str] = []
    excluded = 0
    globs = list(watch_globs)
    ignores = list(ignore_globs)
    for path in paths:
        abs_path = os.path.abspath(os.path.expanduser(path))
        if is_excluded(Path(abs_path)):
            excluded += 1
            continue
        if path_matches_watch(path, globs, cwd):
            if ignores and path_matches_ignore(path, ignores, cwd):
                excluded += 1
                continue
            watched.append(path)
    return watched, excluded
