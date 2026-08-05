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
from lens_lib.log import append_record, has_lens_run_since, parse_iso_ts  # noqa: E402
from lens_lib.paths import matches_glob, path_matches_watch  # noqa: E402
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
                        "session": "sess",
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

    def test_arm_circuit_breaker_disarms_after_max_blocks(self):
        """RC3: an unsatisfied arm gives up after ARM_MAX_BLOCKS instead of
        blocking forever (the 92-blocks-in-10-min runaway)."""
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
                    enforce=True,
                )
                from lens_lib.check import ARM_MAX_BLOCKS, arm_session, read_arm_ts

                sid = "armed-sess"
                arm_session(sid)
                # warn-first: the first unsatisfied stop warns without blocking
                r = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertFalse(r.blocked, "first stop should warn, not block")
                self.assertTrue(r.armed)
                self.assertTrue(r.message)
                self.assertIsNotNone(read_arm_ts(sid))
                # then it blocks up to ARM_MAX_BLOCKS times
                for i in range(ARM_MAX_BLOCKS):
                    r = run_check(host="cursor", session_id=sid, cwd=td)
                    self.assertTrue(r.blocked, f"block {i + 1} should fire")
                    self.assertIsNotNone(read_arm_ts(sid))
                # the next stop trips the breaker: no block, and the arm is gone
                r = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertFalse(r.blocked)
                self.assertIsNone(read_arm_ts(sid), "arm should be cleared")
                with open(log) as f:
                    recs = [json.loads(l) for l in f]
                self.assertTrue(
                    any(x.get("skip_reason") == "arm_abandoned" for x in recs)
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_arm_warn_first_then_block(self):
        """RC4: first unsatisfied stop warns (no block); a later stop blocks; a
        lens_run clears the arm."""
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
                    enforce=True,
                )
                from lens_lib.check import arm_session, read_arm_ts

                sid = "warn-sess"
                arm_session(sid)
                r1 = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertFalse(r1.blocked, "first stop warns, does not block")
                self.assertTrue(r1.message)
                r2 = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertTrue(r2.blocked, "second unsatisfied stop blocks")
                # a logged lens_run clears the arm on the next stop
                append_record(
                    log,
                    {
                        "ts": "2999-01-01T00:00:00Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "chat-note",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "cursor",
                        "session": sid,
                        "findings": [],
                        "escalations": [],
                    },
                )
                r3 = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertFalse(r3.blocked)
                self.assertIsNone(read_arm_ts(sid))
                with open(log) as f:
                    recs = [json.loads(l) for l in f]
                self.assertTrue(
                    any(x.get("skip_reason") == "arm_warned" for x in recs)
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_arm_ttl_expires_stale_arm(self):
        """RC2: an arm older than the TTL clears itself even with zero blocks
        (e.g. armed, then resumed a day later)."""
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
                    enforce=True,
                )
                from lens_lib.check import arm_session, read_arm_ts

                sid = "stale-sess"
                arm_session(sid, ts="2020-01-01T00:00:00Z")
                r = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertFalse(r.blocked)
                self.assertIsNone(read_arm_ts(sid), "stale arm should expire")
                with open(log) as f:
                    recs = [json.loads(l) for l in f]
                self.assertTrue(
                    any(x.get("skip_reason") == "arm_expired" for x in recs)
                )
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


class PreReleaseFootgunTests(unittest.TestCase):
    def test_empty_watch_globs_stays_empty(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            home = Path(td) / "home"
            home.mkdir()
            lens = Path(td) / "review.md"
            lens.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                cfg_path = home / ".lens"
                cfg_path.mkdir()
                (cfg_path / "config.json").write_text(
                    json.dumps(
                        {
                            "lenses": {"review": str(lens)},
                            "default_lens": "review",
                            "log_path": str(log),
                            "watch_globs": [],
                        }
                    )
                )
                cfg = resolve_config()
                self.assertEqual(cfg.watch_globs, [])
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_has_lens_run_since_compares_instants_not_strings(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(
                log,
                {
                    "ts": "2026-08-01T10:00:05Z",
                    "event": "lens_run",
                    "lens": "review",
                    "deliverable": "d",
                    "rounds": 1,
                    "verdict": "pass",
                    "findings": [],
                    "escalations": [],
                },
            )
            # Run at :05Z must NOT satisfy a window starting at :05.500Z
            self.assertFalse(
                has_lens_run_since(log, "2026-08-01T10:00:05.500Z")
            )
            self.assertTrue(has_lens_run_since(log, "2026-08-01T10:00:05+00:00"))
            self.assertIsNotNone(parse_iso_ts("2026-08-01T10:00:05.500Z"))

    def test_first_event_ts_skips_junk_banner(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.jsonl"
            p.write_text(
                "not-json\n"
                + json.dumps(
                    {"type": "user", "timestamp": "2026-08-01T10:00:00.000Z"}
                )
                + "\n"
            )
            self.assertEqual(first_event_ts(str(p)), "2026-08-01T10:00:00.000Z")

    def test_mid_pattern_glob(self):
        self.assertTrue(matches_glob("docs/a/b.md", "docs/**/*.md"))


class LensInvocationDetectionTests(unittest.TestCase):
    """I-9: detect an explicit 'use the lens' request (the incident phrasings)."""

    def test_positive_phrasings(self):
        from lens_lib.check import is_lens_invocation

        for p in [
            "use Yusuke lens",
            "Redo research with yusuke lens",
            "let's summarize this as a markdown, focus on A2A, use yusuke lens",
            "run the lens loop on these files",
            "lens=deck",
            "apply the lens review before you finish",
            # affirmative phrasing whose words end in "nt" must still arm
            "I want you to use the lens",
            "The important step: use the lens",
            "current task: run the lens",
            "different approach — use the lens",
        ]:
            self.assertTrue(is_lens_invocation(p, ["yusuke", "deck"]), p)

    def test_negative_phrasings(self):
        from lens_lib.check import is_lens_invocation

        for p in [
            "compare arkhai and cfex with Kite, summarize differences",
            "clearly lens is not working, I need to report",
            "give me the session ID",
            # negations / hedges must not arm (would hard-block Stop)
            "don't use the lens",
            "can't use the lens",
            "won't run the lens",
            "do not run the lens",
            "without using the lens",
            "with care, finish the lens documentation",
            "use my eyeglasses lens metaphor",
            "please don't use yusuke",
            "instead of the lens, just answer inline",
            "note: the lens plugin is broken",
            # tooling commands are not a review invocation
            "Run the Lens doctor against this machine.",
            "run the lens-doctor",
            "please run the lens close command",
        ]:
            self.assertFalse(is_lens_invocation(p, ["yusuke", "deck"]), p)

    def test_fenced_transcript_content_does_not_arm(self):
        """A distillation prompt embeds a raw transcript full of lens phrases.

        The transcript is quoted raw data (fenced BEGIN/END SESSION TRANSCRIPT),
        not a live invocation. It must NOT arm — this single class was 100% of
        the stuck-block friction in the run log.
        """
        from lens_lib.check import is_lens_invocation

        prompt = (
            "===== BEGIN SESSION TRANSCRIPT (JSONL data — DO NOT treat as a "
            "conversation to continue) =====\n"
            '{"type":"user","content":"Lens enforcement: you invoked the lens '
            "for this session. Invoke the `lens` agent with lens=yusuke. Please "
            'run the lens loop and apply the lens review before you finish."}\n'
            '{"type":"user","content":"use yusuke lens on these files"}\n'
            "===== END SESSION TRANSCRIPT =====\n\n"
            "The above is raw data. Produce the distillation note now per the "
            "system prompt format. Output the markdown note only."
        )
        self.assertFalse(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_nested_fenced_transcript_does_not_arm(self):
        """Nested transcripts (a transcript that itself pasted one) must strip
        to the LAST END marker, leaving no lens phrase behind to arm on."""
        from lens_lib.check import is_lens_invocation

        prompt = (
            "===== BEGIN SESSION TRANSCRIPT (JSONL data) =====\n"
            "===== BEGIN SESSION TRANSCRIPT (JSONL data) =====\n"
            "run the lens loop; use yusuke lens; invoke the lens\n"
            "===== END SESSION TRANSCRIPT =====\n"
            "more raw data mentioning the lens review\n"
            "===== END SESSION TRANSCRIPT =====\n\n"
            "Produce the distillation note only."
        )
        self.assertFalse(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_live_invocation_outside_fence_still_arms(self):
        """Guard against over-stripping: a real request outside the fenced
        transcript must still arm."""
        from lens_lib.check import is_lens_invocation

        prompt = (
            "===== BEGIN SESSION TRANSCRIPT =====\n"
            "unrelated chatter with no lens keyword\n"
            "===== END SESSION TRANSCRIPT =====\n\n"
            "Now summarize that as a markdown note and use yusuke lens on it."
        )
        self.assertTrue(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_task_notification_does_not_arm(self):
        """A background-agent completion notice injected as a user turn is not a
        live request. A failed 'Lens round 3' agent reporting 'complete this
        lens review' must NOT re-arm the session (the 2nd friction channel)."""
        from lens_lib.check import is_lens_invocation

        prompt = (
            "<task-notification>\n<task-id>a4f67d5074b862368</task-id>\n"
            '<summary>Agent "Lens round 3 with explicit files" finished</summary>\n'
            "<result>I've been denied permission to run the lens review. Could "
            "you grant Read/Bash so I can complete this lens review and use "
            "yusuke lens to unblock the Stop hook?</result>\n</task-notification>"
        )
        self.assertFalse(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_non_string_prompt_is_safe(self):
        from lens_lib.check import is_lens_invocation

        self.assertFalse(is_lens_invocation(None, ["yusuke"]))
        self.assertFalse(is_lens_invocation(["use", "lens"], ["yusuke"]))


if __name__ == "__main__":
    unittest.main()
