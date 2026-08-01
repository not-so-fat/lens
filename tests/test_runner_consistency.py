#!/usr/bin/env python3
"""Guard: shared spans in Claude vs Cursor runner agents stay byte-identical (#9)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / "agents" / "lens.md"
CURSOR = ROOT / "agents" / "cursor" / "lens.md"
MARK = re.compile(
    r"<!--\s*SHARED:(?P<name>[\w-]+)\s+START\s*-->\n(?P<body>.*?)\n<!--\s*SHARED:(?P=name)\s+END\s*-->",
    re.DOTALL,
)

REQUIRED = {"role", "paths", "procedure", "reply"}


def shared_blocks(path: Path) -> dict:
    return {
        m.group("name"): m.group("body")
        for m in MARK.finditer(path.read_text(encoding="utf-8"))
    }


class RunnerConsistencyTests(unittest.TestCase):
    def test_shared_blocks_present_and_identical(self):
        c, u = shared_blocks(CLAUDE), shared_blocks(CURSOR)
        self.assertTrue(c, "no SHARED markers in agents/lens.md")
        self.assertTrue(u, "no SHARED markers in agents/cursor/lens.md")
        self.assertEqual(set(c), set(u), f"shared-block names differ: {set(c) ^ set(u)}")
        self.assertTrue(
            REQUIRED <= set(c),
            f"missing required SHARED blocks: {REQUIRED - set(c)}",
        )
        for name in c:
            self.assertEqual(
                c[name],
                u[name],
                f"SHARED:{name} drifted between Claude and Cursor runners",
            )


if __name__ == "__main__":
    unittest.main()
