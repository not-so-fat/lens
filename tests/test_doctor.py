#!/usr/bin/env python3
"""Doctor + named-lens config regression tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from lens_lib.doctor import run_doctor  # noqa: E402

SAMPLE = """---
title: t
---

## Core principle
- x

## When To Run This
- y

## Process

**A?**
- z

## Failure-Mode Guards
- g
"""


class DoctorTests(unittest.TestCase):
    def test_doctor_green_with_named_lens(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            home = td / "home"
            home.mkdir()
            lens = td / "review.md"
            lens.write_text(SAMPLE)
            log = td / "runs.jsonl"
            # sandbox writes under home/.cursor
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            os.environ.pop("LENS_DEFAULT", None)
            try:
                report = run_doctor(
                    fix_sandbox=True,
                    write_log=str(log),
                    write_lens_name="review",
                    write_lens_path=str(lens),
                )
                names = {c.name: c for c in report.checks}
                self.assertTrue(names["config"].ok, names["config"].detail)
                self.assertTrue(names["default_lens"].ok, names["default_lens"].detail)
                self.assertTrue(names["lens_shape"].ok, names["lens_shape"].detail)
                self.assertTrue(names["log_writable"].ok, names["log_writable"].detail)
                self.assertTrue(names["claude_hooks"].ok, names["claude_hooks"].detail)
                self.assertTrue(names["cursor_hooks"].ok, names["cursor_hooks"].detail)
                # Some agent/CI sandboxes block creating `$HOME/.cursor` (EPERM).
                sand = names["cursor_sandbox"]
                if not sand.ok and "Operation not permitted" in sand.detail:
                    self.skipTest(f"cursor sandbox unwritable in this env: {sand.detail}")
                self.assertTrue(sand.ok, sand.detail)
                self.assertTrue(report.ok, [c for c in report.checks if not c.ok])
                cfg = json.loads((home / ".lens" / "config.json").read_text())
                self.assertEqual(cfg["default_lens"], "review")
                self.assertIn("review", cfg["lenses"])
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_doctor_fails_bad_lens_shape(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            home = td / "home"
            home.mkdir()
            lens = td / "bad.md"
            lens.write_text("# no required sections\n")
            log = td / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                report = run_doctor(
                    fix_sandbox=False,
                    write_log=str(log),
                    write_lens_name="bad",
                    write_lens_path=str(lens),
                )
                shape = next(c for c in report.checks if c.name == "lens_shape")
                self.assertFalse(shape.ok)
                self.assertFalse(report.ok)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class HookWiringTests(unittest.TestCase):
    """Doctor must catch an unwired hook script, not just a missing file."""

    def test_missing_required_command_fails(self):
        from lens_lib.doctor import _validate_hook_commands

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            hooks = Path(td_s) / "claude-hooks.json"
            # A hooks file whose Stop is wired to some unrelated command must be
            # flagged for not wiring the required claude_stop.py script.
            hooks.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "echo unrelated",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                )
            )
            ok, detail = _validate_hook_commands(
                host="claude",
                hooks_file=hooks,
                plugin_root=ROOT,
                required_var="CLAUDE_PLUGIN_ROOT",
                required_scripts=[
                    "python/claude_stop.py",
                ],
            )
            self.assertFalse(ok, detail)
            self.assertIn("claude_stop.py", detail)

    def test_shipped_claude_hooks_fully_wired(self):
        from lens_lib.doctor import _validate_hook_commands

        ok, detail = _validate_hook_commands(
            host="claude",
            hooks_file=ROOT / "hooks" / "claude-hooks.json",
            plugin_root=ROOT,
            required_var="CLAUDE_PLUGIN_ROOT",
            required_scripts=[
                "python/claude_stop.py",
                "python/claude_user_prompt.py",
            ],
        )
        self.assertTrue(ok, detail)


class MarketplaceSourceTests(unittest.TestCase):
    """Doctor must flag a moved/deleted directory-source lens marketplace."""

    def _write(self, td: Path, registry: dict) -> Path:
        reg = td / "known_marketplaces.json"
        reg.write_text(json.dumps(registry))
        return reg

    def test_stale_directory_source_fails(self):
        from lens_lib.doctor import _lens_marketplace_source

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            reg = self._write(
                td,
                {
                    "lens-plugins": {
                        "source": {"source": "directory", "path": str(td / "gone")},
                        "installLocation": str(td / "gone"),
                    }
                },
            )
            ok, detail = _lens_marketplace_source(reg)
            self.assertFalse(ok, detail)
            self.assertIn("marketplace add", detail)

    def test_present_directory_source_passes(self):
        from lens_lib.doctor import _lens_marketplace_source

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            here = td / "lens-repo"
            here.mkdir()
            reg = self._write(
                td,
                {"lens-plugins": {"source": {"source": "directory", "path": str(here)}}},
            )
            ok, detail = _lens_marketplace_source(reg)
            self.assertTrue(ok, detail)

    def test_github_source_passes(self):
        from lens_lib.doctor import _lens_marketplace_source

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            reg = self._write(
                td,
                {"lens-plugins": {"source": {"source": "github", "repo": "not-so-fat/lens"}}},
            )
            ok, detail = _lens_marketplace_source(reg)
            self.assertTrue(ok, detail)

    def test_non_lens_directory_source_ignored(self):
        from lens_lib.doctor import _lens_marketplace_source

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            reg = self._write(
                td,
                {"other": {"source": {"source": "directory", "path": str(td / "gone")}}},
            )
            ok, detail = _lens_marketplace_source(reg)
            self.assertTrue(ok, detail)

    def test_missing_registry_skips(self):
        from lens_lib.doctor import _lens_marketplace_source

        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            ok, detail = _lens_marketplace_source(Path(td_s) / "nope.json")
            self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
