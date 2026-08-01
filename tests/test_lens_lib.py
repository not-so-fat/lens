#!/usr/bin/env python3
"""Stdlib unittest suite for lens_lib."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from lens_lib.check import run_check  # noqa: E402
from lens_lib.close import close_deliverable  # noqa: E402
from lens_lib.config import (  # noqa: E402
    ConfigError,
    add_lens,
    resolve_config,
    resolve_lens,
    write_config,
)
from lens_lib.lens_parse import parse_lens_file  # noqa: E402
from lens_lib.log import append_record, has_lens_run_since  # noqa: E402
from lens_lib.paths import path_matches_watch  # noqa: E402
from lens_lib.transcript import first_event_ts, written_paths_from_transcript  # noqa: E402

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


class ConfigTests(unittest.TestCase):
    def test_named_lenses_and_dir(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            home = Path(td) / "home"
            home.mkdir()
            lenses_dir = Path(td) / "dir"
            lenses_dir.mkdir()
            review = Path(td) / "review.md"
            deck = lenses_dir / "deck.md"
            review.write_text(SAMPLE)
            deck.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            os.environ.pop("LENS_DEFAULT", None)
            try:
                write_config(
                    str(log),
                    lenses={"review": str(review)},
                    default_lens="review",
                    lenses_dir=str(lenses_dir),
                )
                cfg = resolve_config()
                name, path = resolve_lens(cfg, "review")
                self.assertEqual(name, "review")
                self.assertEqual(path, review.resolve())
                name2, path2 = resolve_lens(cfg, "deck")
                self.assertEqual(name2, "deck")
                self.assertEqual(path2, deck.resolve())
                with self.assertRaises(ConfigError):
                    resolve_lens(cfg, "missing")
                add_lens("story", str(review))
                cfg2 = resolve_config()
                self.assertIn("story", cfg2.lenses)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_missing_raises(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = td
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                with self.assertRaises(ConfigError):
                    resolve_config()
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class PathsTests(unittest.TestCase):
    def test_md_glob(self):
        cwd = str(ROOT)
        md = str(ROOT / "docs" / "PRD.md")
        py = str(ROOT / "python" / "claude_stop.py")
        self.assertTrue(path_matches_watch(md, ["**/*.md"], cwd))
        self.assertFalse(path_matches_watch(py, ["**/*.md"], cwd))


class TranscriptTests(unittest.TestCase):
    def test_write_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.jsonl"
            lines = [
                {
                    "type": "user",
                    "timestamp": "2026-07-31T12:00:00.000Z",
                    "cwd": "/w",
                    "sessionId": "abc",
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-07-31T12:00:01.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {
                                    "file_path": "/w/out.md",
                                    "content": "hi",
                                },
                            }
                        ],
                    },
                },
            ]
            p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
            self.assertEqual(first_event_ts(str(p)), "2026-07-31T12:00:00.000Z")
            self.assertEqual(written_paths_from_transcript(str(p)), ["/w/out.md"])


class LogAndCheckTests(unittest.TestCase):
    def test_block_without_lens_run(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            lens = Path(td) / "lens.md"
            log = Path(td) / "runs.jsonl"
            lens.write_text(SAMPLE)
            home = Path(td) / "home"
            home.mkdir()
            deliverable = Path(td) / "doc.md"
            deliverable.write_text("x", encoding="utf-8")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log),
                    lenses={"review": str(lens)},
                    default_lens="review",
                    enforce=True,
                )
                transcript = Path(td) / "sess.jsonl"
                transcript.write_text(
                    json.dumps(
                        {
                            "type": "user",
                            "timestamp": "2026-07-31T10:00:00.000Z",
                            "cwd": str(td),
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "type": "assistant",
                            "timestamp": "2026-07-31T10:00:01.000Z",
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_use",
                                        "name": "Write",
                                        "input": {
                                            "file_path": str(deliverable),
                                            "content": "x",
                                        },
                                    }
                                ]
                            },
                        }
                    )
                    + "\n"
                )
                result = run_check(
                    host="claude-code",
                    transcript_path=str(transcript),
                    session_id="sess",
                    cwd=td,
                )
                self.assertTrue(result.watched_writes)
                self.assertFalse(result.lens_run_found)
                self.assertTrue(result.blocked)

                append_record(
                    log,
                    {
                        "ts": "2026-07-31T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "doc",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "findings": [],
                        "escalations": [],
                    },
                )
                self.assertTrue(has_lens_run_since(log, "2026-07-31T10:00:00.000Z"))
                result2 = run_check(
                    host="claude-code",
                    transcript_path=str(transcript),
                    session_id="sess",
                    cwd=td,
                )
                self.assertTrue(result2.lens_run_found)
                self.assertFalse(result2.blocked)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_close_requires_lens_run(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            lens = Path(td) / "lens.md"
            log = Path(td) / "runs.jsonl"
            lens.write_text(SAMPLE)
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log),
                    lenses={"review": str(lens)},
                    default_lens="review",
                )
                with self.assertRaises(ValueError):
                    close_deliverable("missing", 0)
                append_record(
                    log,
                    {
                        "ts": "2026-07-31T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "d1",
                        "rounds": 1,
                        "verdict": "pass",
                        "findings": [],
                        "escalations": [],
                    },
                )
                rec, _ = close_deliverable("d1", 0)
                self.assertEqual(rec["event"], "human_review")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class LensParseTests(unittest.TestCase):
    def test_sample_lens_shape(self):
        path = ROOT / "tests" / "fixtures" / "sample_lens.md"
        result = parse_lens_file(path)
        self.assertTrue(result.ok, result.errors)
        self.assertGreaterEqual(result.check_blocks, 1)


if __name__ == "__main__":
    unittest.main()
