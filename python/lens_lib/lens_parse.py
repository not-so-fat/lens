"""Lens markdown shape validation and patch apply (§7.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REQUIRED_HEADINGS = [
    "## Core principle",
    "## When To Run This",
    "## Process",
    "## Failure-Mode Guards",
]

# Bold question blocks like **Simplest?** or **Argument?** — when …
CHECK_BLOCK_RE = re.compile(r"^\*\*[^*]+\?\*\*", re.MULTILINE)
CHECK_SLUG_COMMENT_RE = re.compile(r"<!--\s*check:\s*([a-z0-9]+(?:-[a-z0-9]+)*)\s*-->")


@dataclass
class LensParseResult:
    ok: bool
    path: Path
    errors: List[str]
    check_blocks: int = 0


def parse_lens_file(path: Path) -> LensParseResult:
    errors: List[str] = []
    if not path.is_file():
        return LensParseResult(ok=False, path=path, errors=[f"not found: {path}"])

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append("missing YAML frontmatter")
    else:
        end = text.find("\n---", 3)
        if end < 0:
            errors.append("unterminated YAML frontmatter")

    positions: List[tuple[str, int]] = []
    for h in REQUIRED_HEADINGS:
        idx = text.find(h)
        if idx < 0:
            errors.append(f"missing heading: {h}")
        else:
            positions.append((h, idx))

    for i in range(len(positions) - 1):
        if positions[i][1] > positions[i + 1][1]:
            errors.append(
                f"heading order: {positions[i][0]} must precede {positions[i + 1][0]}"
            )

    check_blocks = len(CHECK_BLOCK_RE.findall(text))
    if "## Process" in text and check_blocks == 0:
        errors.append("## Process contains no **<Check block>?** question blocks")

    return LensParseResult(
        ok=len(errors) == 0,
        path=path,
        errors=errors,
        check_blocks=check_blocks,
    )


def _section_bounds(text: str, heading: str, next_heading: Optional[str]) -> Tuple[int, int]:
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"missing heading: {heading}")
    body_start = start + len(heading)
    if next_heading:
        end = text.find(next_heading, body_start)
        if end < 0:
            raise ValueError(f"missing heading after {heading}: {next_heading}")
    else:
        end = len(text)
    return body_start, end


def _normalize_bullet(bullet: str) -> str:
    b = bullet.strip()
    if not b.startswith("-"):
        b = "- " + b
    return b


def _find_check_block_lines(lines: List[str], slug: str) -> Optional[int]:
    """Return index of **Block?** line for slug, or None."""
    for i, line in enumerate(lines):
        if CHECK_SLUG_COMMENT_RE.search(line) and CHECK_SLUG_COMMENT_RE.search(line).group(1) == slug:
            for j in range(i + 1, len(lines)):
                if CHECK_BLOCK_RE.match(lines[j].strip()):
                    return j
        if CHECK_BLOCK_RE.match(line.strip()):
            for j in range(max(0, i - 2), i):
                m = CHECK_SLUG_COMMENT_RE.search(lines[j])
                if m and m.group(1) == slug:
                    return i
    return None


def apply_lens_ops(text: str, ops: List[dict]) -> str:
    """Apply correction-capture ops to lens markdown text."""
    out = text
    for op in ops:
        kind = op.get("op")
        if kind == "add_check":
            out = _apply_add_check(out, op)
        elif kind == "amend_check":
            out = _apply_amend_check(out, op)
        elif kind == "add_guard":
            out = _apply_add_guard(out, op)
        else:
            raise ValueError(f"unknown op: {kind!r}")
    return out


def _apply_add_check(text: str, op: dict) -> str:
    block = op["block"].strip()
    if not block.startswith("**"):
        block = f"**{block.rstrip('?')}?**"
    bullet = _normalize_bullet(op["bullet"])
    slug = op.get("check")
    slug_line = f"<!-- check: {slug} -->\n" if slug else ""
    chunk = f"\n{slug_line}{block}\n{bullet}\n"

    proc_start, proc_end = _section_bounds(text, "## Process", "## Failure-Mode Guards")
    section = text[proc_start:proc_end]
    finish_idx = section.lower().find("\nfinish:")
    if finish_idx >= 0:
        insert_at = proc_start + finish_idx
    else:
        insert_at = proc_end
    return text[:insert_at] + chunk + text[insert_at:]


def _apply_amend_check(text: str, op: dict) -> str:
    slug = op["check"]
    bullet = _normalize_bullet(op["bullet"])
    proc_start, proc_end = _section_bounds(text, "## Process", "## Failure-Mode Guards")
    section = text[proc_start:proc_end]
    lines = section.splitlines()
    block_idx = _find_check_block_lines(lines, slug)
    if block_idx is None:
        raise ValueError(f"no Process check block for slug {slug!r}")

    # Rebuild section with replaced first bullet after block header.
    new_lines = list(lines)
    inserted = False
    for i in range(block_idx + 1, len(new_lines)):
        stripped = new_lines[i].strip()
        if CHECK_BLOCK_RE.match(stripped) or stripped.startswith("##"):
            new_lines.insert(i, bullet)
            inserted = True
            break
        if stripped.startswith("- "):
            new_lines[i] = bullet
            inserted = True
            break
    if not inserted:
        new_lines.insert(block_idx + 1, bullet)
    new_section = "\n".join(new_lines)
    if section.endswith("\n"):
        new_section += "\n"
    return text[:proc_start] + new_section + text[proc_end:]


def _apply_add_guard(text: str, op: dict) -> str:
    bullet = _normalize_bullet(op["bullet"])
    guard_start, guard_end = _section_bounds(text, "## Failure-Mode Guards", None)
    return text[:guard_end].rstrip() + "\n" + bullet + "\n" + text[guard_end:]


def render_patch_diff(before: str, after: str, path: Path) -> str:
    """Simple unified diff preview for CLI show."""
    import difflib

    lines = list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + " (proposed)",
            lineterm="",
        )
    )
    return "".join(lines) if lines else "(no changes)\n"


def slug_markers_in_process(text: str) -> Dict[str, str]:
    """Map check slug → block title from <!-- check: slug --> markers."""
    proc_start, proc_end = _section_bounds(text, "## Process", "## Failure-Mode Guards")
    section = text[proc_start:proc_end]
    lines = section.splitlines()
    out: Dict[str, str] = {}
    pending_slug: Optional[str] = None
    for line in lines:
        m = CHECK_SLUG_COMMENT_RE.search(line)
        if m:
            pending_slug = m.group(1)
            continue
        if CHECK_BLOCK_RE.match(line.strip()) and pending_slug:
            out[pending_slug] = line.strip()
            pending_slug = None
    return out
