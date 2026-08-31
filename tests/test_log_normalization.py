#!/usr/bin/env python3
"""Run-log schema version and legacy read normalization (NOT-39)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from lens_lib.corrections import funnel_stats  # noqa: E402
from lens_lib.log import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    append_record,
    deliverable_has_lens_run,
    has_lens_run_since,
    iter_records,
    list_lens_runs_for_deliverable,
    normalize_record,
)


FIXTURE = ROOT / "tests" / "fixtures" / "legacy_lens_runs.jsonl"


class LogNormalizationTests(unittest.TestCase):
    def test_legacy_row_without_event(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])
        norm = normalize_record(raw)
        self.assertEqual(norm["event"], "lens_run")
        self.assertEqual(norm["verdict"], "pass")
        self.assertEqual(norm["rounds"], 1)
        self.assertEqual(norm["escalations"], [])
        self.assertEqual(norm["host"], "claude-code")

    def test_default_lens_name_alias(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[1])
        norm = normalize_record(raw)
        self.assertEqual(norm["lens"], "default_lens")

    def test_default_lens_name_unchanged(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[2])
        norm = normalize_record(raw)
        self.assertEqual(norm["lens"], "default_lens")

    def test_iter_records_applies_normalization(self):
        runs = list(iter_records(FIXTURE))
        self.assertEqual(len(runs), 3)
        legacy = next(r for r in runs if r.get("deliverable") == "transcript-distillation")
        self.assertEqual(legacy["event"], "lens_run")
        self.assertEqual(legacy["verdict"], "pass")
        aliased = next(r for r in runs if r.get("deliverable") == "sample-doc")
        self.assertEqual(aliased["lens"], "default_lens")

    def test_append_stamps_schema_version(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(
                log,
                {
                    "event": "lens_run",
                    "lens": "review",
                    "deliverable": "x",
                    "rounds": 1,
                    "verdict": "pass",
                    "findings": [],
                    "escalations": [],
                    "run_id": "lr_abc123456789abc",
                },
            )
            raw = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual(raw["schema_version"], CURRENT_SCHEMA_VERSION)

    def test_legacy_row_counts_in_gate_and_analytics(self):
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            shutil.copy(FIXTURE, log)
            self.assertTrue(deliverable_has_lens_run(log, "transcript-distillation"))
            self.assertTrue(
                has_lens_run_since(log, "2026-08-04T00:00:00Z"),
            )
            runs = list_lens_runs_for_deliverable(log, "sample-doc")
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["lens"], "default_lens")
            stats = funnel_stats(log_path=log)
            self.assertEqual(stats["terminal_lens_runs"], 3)


if __name__ == "__main__":
    unittest.main()
