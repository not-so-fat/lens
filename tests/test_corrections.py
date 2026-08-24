#!/usr/bin/env python3
"""Correction capture tests (SC-1..5)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from lens_lib.close import close_deliverable  # noqa: E402
from lens_lib.config import write_config  # noqa: E402
from lens_lib.corrections import (  # noqa: E402
    apply_patch,
    get_signal,
    list_signals,
    propose_patch,
    validate_correction_signal,
    validate_lens_patch,
)
from lens_lib.lens_parse import apply_lens_ops, parse_lens_file  # noqa: E402
from lens_lib.log import append_record  # noqa: E402
from lens_lib.util import correction_signals_path, lens_patches_path  # noqa: E402

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

LENS_WITH_SLUG = """---
title: t
---

## Core principle
- x

## When To Run This
- y

## Process

<!-- check: source-grounded -->
**Source grounded?**
- Cite sources.

Finish: re-sweep once after editing.

## Failure-Mode Guards
- g
"""


class CorrectionCaptureTests(unittest.TestCase):
    def _home(self):
        td = tempfile.TemporaryDirectory(dir=str(ROOT))
        home = Path(td.name) / "home"
        home.mkdir()
        lens = Path(td.name) / "lens.md"
        log = Path(td.name) / "runs.jsonl"
        lens.write_text(LENS_WITH_SLUG, encoding="utf-8")
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        os.environ.pop("LENS_LOG_PATH", None)
        write_config(
            str(log),
            lenses={"review": str(lens)},
            default_lens="review",
        )
        append_record(
            log,
            {
                "ts": "2026-08-23T09:55:00Z",
                "event": "lens_run",
                "lens": "review",
                "deliverable": "d1",
                "rounds": 1,
                "verdict": "pass",
                "findings": [],
                "escalations": [],
            },
        )
        return td, home, lens, log, old_home

    def test_close_appends_miss_and_noise_signals(self):
        td, home, lens, log, old_home = self._home()
        try:
            _, _, signals = close_deliverable(
                "d1",
                1,
                misses=["source-grounded:Rating must stay human-owned."],
                noise=["source-grounded:False positive on cite."],
            )
            self.assertEqual(len(signals), 2)
            kinds = {s["kind"] for s in signals}
            self.assertEqual(kinds, {"miss", "noise"})
            for sig in signals:
                self.assertEqual(validate_correction_signal(sig), [])
                self.assertEqual(sig["status"], "open")
                self.assertEqual(sig["lens"], "review")
            lines = correction_signals_path().read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            rec, _, signals2 = close_deliverable(
                "d1",
                0,
                misses=["source-grounded:Again."],
            )
            self.assertEqual(len(signals2), 1)
            lines2 = correction_signals_path().read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines2), 3)
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_propose_requires_two_signals_or_force(self):
        td, home, lens, log, old_home = self._home()
        try:
            _, _, signals = close_deliverable(
                "d1",
                1,
                misses=["source-grounded:one"],
            )
            ops = [{"op": "add_guard", "bullet": "Do not infer ratings."}]
            with self.assertRaises(ValueError):
                propose_patch(
                    lens="review",
                    signal_ids=[signals[0]["id"]],
                    ops=ops,
                )
            _, _, signals2 = close_deliverable(
                "d1",
                0,
                misses=["source-grounded:two"],
            )
            patch = propose_patch(
                lens="review",
                signal_ids=[signals[0]["id"], signals2[0]["id"]],
                ops=ops,
            )
            self.assertEqual(validate_lens_patch(patch), [])
            self.assertEqual(patch["status"], "proposed")
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_noise_only_rejects_add_check(self):
        td, home, lens, log, old_home = self._home()
        try:
            _, _, s1 = close_deliverable(
                "d1", 0, noise=["source-grounded:n1"]
            )
            _, _, s2 = close_deliverable(
                "d1", 0, noise=["source-grounded:n2"]
            )
            with self.assertRaises(ValueError):
                propose_patch(
                    lens="review",
                    signal_ids=[s1[0]["id"], s2[0]["id"]],
                    ops=[
                        {
                            "op": "add_check",
                            "block": "New?",
                            "bullet": "x",
                            "check": "new-term",
                        }
                    ],
                )
            patch = propose_patch(
                lens="review",
                signal_ids=[s1[0]["id"], s2[0]["id"]],
                ops=[{"op": "add_guard", "bullet": "Tighten cite rule."}],
            )
            self.assertEqual(patch["ops"][0]["op"], "add_guard")
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_apply_updates_lens_and_marks_signals(self):
        td, home, lens, log, old_home = self._home()
        try:
            _, _, s1 = close_deliverable(
                "d1", 0, misses=["source-grounded:a"]
            )
            _, _, s2 = close_deliverable(
                "d1", 0, misses=["source-grounded:b"]
            )
            patch = propose_patch(
                lens="review",
                signal_ids=[s1[0]["id"], s2[0]["id"]],
                ops=[
                    {
                        "op": "amend_check",
                        "check": "source-grounded",
                        "bullet": "- Do not infer ratings; cite or escalate.",
                    }
                ],
            )
            path, accepted = apply_patch(patch["id"])
            self.assertEqual(accepted["status"], "accepted")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Do not infer ratings", text)
            parsed = parse_lens_file(path)
            self.assertTrue(parsed.ok, parsed.errors)
            self.assertEqual(get_signal(s1[0]["id"])["status"], "actioned")
            self.assertEqual(get_signal(s2[0]["id"])["status"], "actioned")
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_apply_rejects_wrong_lens_path(self):
        td, home, lens, log, old_home = self._home()
        try:
            _, _, s1 = close_deliverable("d1", 0, misses=["source-grounded:a"])
            _, _, s2 = close_deliverable("d1", 0, misses=["source-grounded:b"])
            from lens_lib.corrections import append_patch

            bad = {
                "id": "lp_deadbeef1234",
                "status": "proposed",
                "lens": "review",
                "lens_path": "/tmp/not-configured.md",
                "ops": [{"op": "add_guard", "bullet": "x"}],
                "signal_ids": [s1[0]["id"], s2[0]["id"]],
                "created_at": "2026-08-23T10:00:00Z",
            }
            append_patch(bad)
            with self.assertRaises(ValueError):
                apply_patch(bad["id"])
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_lens_parse_ops(self):
        out = apply_lens_ops(
            LENS_WITH_SLUG,
            [
                {"op": "add_guard", "bullet": "No invented scores."},
                {
                    "op": "add_check",
                    "block": "Intent grounded?",
                    "bullet": "Match user ask.",
                    "check": "intent-grounded",
                },
            ],
        )
        self.assertIn("No invented scores.", out)
        self.assertIn("<!-- check: intent-grounded -->", out)
        self.assertIn("**Intent grounded?**", out)

    def test_cli_list_and_apply(self):
        td, home, lens, log, old_home = self._home()
        try:
            from lens_lib.__main__ import main

            close_deliverable("d1", 0, misses=["source-grounded:a"])
            close_deliverable("d1", 0, misses=["source-grounded:b"])
            sigs = list_signals()
            ops_file = Path(td.name) / "ops.json"
            ops_file.write_text(
                json.dumps([{"op": "add_guard", "bullet": "Guard from CLI."}]),
                encoding="utf-8",
            )
            rc = main(
                [
                    "corrections",
                    "propose",
                    "--lens",
                    "review",
                    "--signal-ids",
                    f"{sigs[0]['id']},{sigs[1]['id']}",
                    "--ops-file",
                    str(ops_file),
                ]
            )
            self.assertEqual(rc, 0)
            patches = [
                json.loads(l)
                for l in lens_patches_path().read_text(encoding="utf-8").splitlines()
                if l.strip()
            ]
            patch_id = patches[-1]["id"]
            rc2 = main(["corrections", "apply", patch_id])
            self.assertEqual(rc2, 0)
            self.assertIn("Guard from CLI.", lens.read_text(encoding="utf-8"))
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
