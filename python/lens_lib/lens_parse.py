"""Lens markdown shape validation (§7.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


REQUIRED_HEADINGS = [
    "## Core principle",
    "## When To Run This",
    "## Process",
    "## Failure-Mode Guards",
]

# Bold question blocks like **Simplest?** or **Argument?** — when …
CHECK_BLOCK_RE = re.compile(r"^\*\*[^*]+\?\*\*", re.MULTILINE)


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

    # Heading order: required headings appear in order (extra sections allowed)
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


def default_lens_path(vault_root: Path, lens: str) -> Path:
    return vault_root / "Direction" / "Lenses" / f"{lens}.md"


def find_lens(vault_root: Path, lens: str) -> Optional[Path]:
    path = default_lens_path(vault_root, lens)
    return path if path.is_file() else None


def discover_lens_name(vault_root: Path) -> Optional[str]:
    """First *.md stem under Direction/Lenses/ (sorted), if any."""
    lenses = vault_root / "Direction" / "Lenses"
    if not lenses.is_dir():
        return None
    names = sorted(p.stem for p in lenses.glob("*.md") if p.is_file())
    return names[0] if names else None
