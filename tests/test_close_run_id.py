#!/usr/bin/env python3
"""NOT-37 / NOT-42: run_id attribution and owner-review close."""

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
from lens_lib.corrections import funnel_stats  # noqa: E402
from lens_lib.log import append_record, new_run_id  # noqa: E402
from lens_lib.__main__ import main  # noqa: E402


def _terminal_run(
    *,
    deliverable: str,
    lens: str,
    run_id: str,
    ts: str,
    session: str | None = None,
) -> dict:
    rec = {
        "ts": ts,
        "event": "lens_run",
        "run_id": run_id,
        "lens": lens,
        "deliverable": deliverable,
        "rounds": 1,
        "verdict": "pass",
        "findings": [],
        "escalations": [],
    }
    if session:
        rec["session"] = session
    return rec


class CloseRunIdTests(unittest.TestCase):
    def _home(self):
        td = tempfile.TemporaryDirectory(dir=str(ROOT))
        home = Path(td.name) / "home"
        home.mkdir()
        lens = Path(td.name) / "lens.md"
        log = Path(td.name) / "runs.jsonl"
        lens.write_text(
            """---
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
""",
            encoding="utf-8",
        )
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        os.environ.pop("LENS_LOG_PATH", None)
        write_config(
            str(log),
            lenses={"yusuke": str(lens), "chi-business": str(lens)},
            default_lens="yusuke",
        )
        return td, home, lens, log, old_home

    def test_ambiguous_deliverable_only_close_rejected(self):
        td, home, lens, log, old_home = self._home()
        try:
            d = "detailed-user-stories-trust-chain"
            append_record(
                log,
                _terminal_run(
                    deliverable=d,
                    lens="chi-business",
                    run_id="lr_c111111111111111",
                    ts="2026-08-29T08:57:09Z",
                    session="s1",
                ),
            )
            append_record(
                log,
                _terminal_run(
                    deliverable=d,
                    lens="yusuke",
                    run_id="lr_y222222222222222",
                    ts="2026-08-29T08:58:54Z",
                    session="s2",
                ),
            )
            with self.assertRaises(ValueError) as ctx:
                close_deliverable(d, 0)
            self.assertIn("candidates", str(ctx.exception))
            self.assertIn("lr_c111111111111111", str(ctx.exception))
            self.assertIn("lr_y222222222222222", str(ctx.exception))
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_run_id_close_attributes_correct_lens(self):
        td, home, lens, log, old_home = self._home()
        try:
            d = "detailed-user-stories-trust-chain"
            append_record(
                log,
                _terminal_run(
                    deliverable=d,
                    lens="chi-business",
                    run_id="lr_c111111111111111",
                    ts="2026-08-29T08:57:09Z",
                ),
            )
            append_record(
                log,
                _terminal_run(
                    deliverable=d,
                    lens="yusuke",
                    run_id="lr_y222222222222222",
                    ts="2026-08-29T08:58:54Z",
                ),
            )
            _, _, signals = close_deliverable(
                d,
                1,
                run_id="lr_c111111111111111",
                misses=["source-grounded:missed rating rule"],
            )
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["lens"], "chi-business")
            self.assertEqual(signals[0]["lens_run_id"], "lr_c111111111111111")
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_close_by_run_id_without_deliverable(self):
        td, home, lens, log, old_home = self._home()
        try:
            run_id = "lr_only333333333333"
            append_record(
                log,
                _terminal_run(
                    deliverable="d1",
                    lens="yusuke",
                    run_id=run_id,
                    ts="2026-08-29T09:00:00Z",
                ),
            )
            rec, _, _ = close_deliverable(None, 0, run_id=run_id)
            self.assertEqual(rec["deliverable"], "d1")
            self.assertEqual(rec["lens_run_id"], run_id)
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_duplicate_human_review_for_run_id_rejected(self):
        td, home, lens, log, old_home = self._home()
        try:
            run_id = "lr_dup44444444444444"
            append_record(
                log,
                _terminal_run(
                    deliverable="d1",
                    lens="yusuke",
                    run_id=run_id,
                    ts="2026-08-29T09:00:00Z",
                ),
            )
            close_deliverable("d1", 0, run_id=run_id)
            with self.assertRaises(ValueError):
                close_deliverable("d1", 0, run_id=run_id)
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_append_run_assigns_run_id(self):
        td, home, lens, log, old_home = self._home()
        try:
            payload = json.dumps(
                {
                    "ts": "2026-08-29T09:00:00Z",
                    "lens": "yusuke",
                    "deliverable": "d-append",
                    "rounds": 1,
                    "verdict": "pass",
                    "findings": [],
                    "escalations": [],
                }
            )
            rc = main(["append-run", "--json", payload])
            self.assertEqual(rc, 0)
            lines = log.read_text(encoding="utf-8").strip().splitlines()
            rec = json.loads(lines[-1])
            self.assertTrue(rec.get("run_id", "").startswith("lr_"))
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_runs_list_and_funnel_cli(self):
        td, home, lens, log, old_home = self._home()
        try:
            append_record(
                log,
                _terminal_run(
                    deliverable="d1",
                    lens="yusuke",
                    run_id=new_run_id(),
                    ts="2026-08-29T09:00:00Z",
                ),
            )
            close_deliverable("d1", 0)
            rc = main(["runs", "list", "--deliverable", "d1"])
            self.assertEqual(rc, 0)
            rc2 = main(["corrections", "funnel"])
            self.assertEqual(rc2, 0)
            stats = funnel_stats(log_path=log)
            self.assertEqual(stats["terminal_lens_runs"], 1)
            self.assertEqual(stats["human_reviews"], 1)
        finally:
            td.cleanup()
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
