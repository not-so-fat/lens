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
from lens_lib.config import ConfigError, resolve_config, write_config  # noqa: E402
from lens_lib.lens_parse import parse_lens_file  # noqa: E402
from lens_lib.log import append_record, has_lens_run_since  # noqa: E402
from lens_lib.paths import path_matches_watch  # noqa: E402
from lens_lib.transcript import first_event_ts, written_paths_from_transcript  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_env_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            vault.mkdir()
            old = os.environ.get("LENS_VAULT_ROOT")
            os.environ["LENS_VAULT_ROOT"] = str(vault)
            try:
                cfg = resolve_config()
                self.assertEqual(cfg.vault_root, vault.resolve())
                self.assertIn(cfg.source, ("env", "env+config"))
            finally:
                if old is None:
                    os.environ.pop("LENS_VAULT_ROOT", None)
                else:
                    os.environ["LENS_VAULT_ROOT"] = old

    def test_missing_raises(self):
        old = os.environ.pop("LENS_VAULT_ROOT", None)
        # Point HOME at empty temp so ~/.lens is missing
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = td
            try:
                with self.assertRaises(ConfigError):
                    resolve_config()
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
                if old is not None:
                    os.environ["LENS_VAULT_ROOT"] = old


class PathsTests(unittest.TestCase):
    def test_md_glob(self):
        # Avoid system temp — excluded by §7.4
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
        # Keep written deliverable outside system temp (excluded by §7.4)
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            vault = Path(td) / "vault"
            (vault / "Metadata" / "usage").mkdir(parents=True)
            (vault / "Direction" / "Lenses").mkdir(parents=True)
            home = Path(td) / "home"
            home.mkdir()
            deliverable = Path(td) / "doc.md"
            deliverable.write_text("x", encoding="utf-8")
            old_home = os.environ.get("HOME")
            old_env = os.environ.get("LENS_VAULT_ROOT")
            os.environ["HOME"] = str(home)
            os.environ["LENS_VAULT_ROOT"] = str(vault)
            try:
                write_config(str(vault), enforce=True)
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
                self.assertIn("Invoke the `lens` agent", result.message)

                append_record(
                    vault,
                    {
                        "ts": "2026-07-31T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "yusuke",
                        "area": "kite",
                        "deliverable": "doc",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "findings": [],
                        "escalations": [],
                    },
                )
                self.assertTrue(has_lens_run_since(vault, "2026-07-31T10:00:00.000Z"))
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
                if old_env is None:
                    os.environ.pop("LENS_VAULT_ROOT", None)
                else:
                    os.environ["LENS_VAULT_ROOT"] = old_env

    def test_close_requires_lens_run(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            (vault / "Metadata" / "usage").mkdir(parents=True)
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            old_env = os.environ.get("LENS_VAULT_ROOT")
            os.environ["HOME"] = str(home)
            os.environ["LENS_VAULT_ROOT"] = str(vault)
            try:
                write_config(str(vault))
                with self.assertRaises(ValueError):
                    close_deliverable("missing", 0)
                append_record(
                    vault,
                    {
                        "ts": "2026-07-31T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "yusuke",
                        "area": "kite",
                        "deliverable": "d1",
                        "rounds": 1,
                        "verdict": "pass",
                        "findings": [],
                        "escalations": [],
                    },
                )
                rec, _ = close_deliverable("d1", 0)
                self.assertEqual(rec["event"], "human_review")
                self.assertEqual(rec["corrections"], 0)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
                if old_env is None:
                    os.environ.pop("LENS_VAULT_ROOT", None)
                else:
                    os.environ["LENS_VAULT_ROOT"] = old_env


class LensParseTests(unittest.TestCase):
    def test_yusuke_shape(self):
        path = Path(
            "/Users/not_so_fat/workspace/obsidian/lexicon-personal/Direction/Lenses/yusuke.md"
        )
        if not path.is_file():
            self.skipTest("vault lens not present")
        result = parse_lens_file(path)
        self.assertTrue(result.ok, result.errors)
        self.assertGreaterEqual(result.check_blocks, 1)


if __name__ == "__main__":
    unittest.main()
