#!/usr/bin/env python3
"""Stdlib unittest suite for lens_lib."""

from __future__ import annotations

import json
import os
import subprocess
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
from lens_lib.paths import (  # noqa: E402
    filter_watched,
    load_lensignore,
    matches_glob,
    path_matches_watch,
)
from lens_lib.check import arm_session, armed_session_ids  # noqa: E402
from lens_lib.log import has_lens_run_for_sessions  # noqa: E402
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

    def test_watched_write_block_preserves_arm_warn_budget(self):
        """Fix: a watched-write stop blocks on its own strong signal and must
        not consume the arm's warn/breaker budget (which is for the weaker
        prompt-text heuristic)."""
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
                from lens_lib.check import (
                    arm_session,
                    record_sidechannel_write,
                    session_armed_path,
                )

                sid = "armed-write-sess"
                arm_session(sid)
                deliverable = Path(td) / "note.md"
                deliverable.write_text("x", encoding="utf-8")
                record_sidechannel_write(sid, str(deliverable), workspace_root=td)
                r = run_check(host="cursor", session_id=sid, cwd=td)
                self.assertTrue(r.blocked, "watched write with no lens_run blocks")
                # the arm's block counter (line 2 of armed.txt) is untouched —
                # the write-block did not spend a warn/breaker attempt.
                armed = session_armed_path(sid)
                self.assertEqual(
                    len(armed.read_text(encoding="utf-8").splitlines()),
                    1,
                    "write-block must not consume the arm counter",
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
                rec, _, _ = close_deliverable("d1", 0)
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
            # "close" here is natural language, not the /lens-close tooling
            "run the lens close to the product thesis",
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


class LensRunDedupTests(unittest.TestCase):
    """A spurious gate re-block can prompt the worker to re-log the same terminal
    run; append-run drops the identical re-append."""

    def _rec(self, **kw):
        base = {
            "event": "lens_run", "lens": "review", "deliverable": "d", "rounds": 7,
            "verdict": "pass", "findings": [], "escalations": [],
            "session": "s1", "ts": "2026-08-04T18:05:25Z",
        }
        base.update(kw)
        return base

    def test_identity_match_and_boundaries(self):
        from lens_lib.log import append_record, is_duplicate_lens_run

        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(log, self._rec())
            # same session+deliverable+rounds, later ts -> duplicate
            self.assertTrue(
                is_duplicate_lens_run(log, self._rec(ts="2026-08-04T18:06:16Z"))
            )
            # next round -> legitimate, not a duplicate
            self.assertFalse(
                is_duplicate_lens_run(log, self._rec(rounds=8, ts="2026-08-04T18:10:00Z"))
            )
            # different session, same deliverable/round -> not a duplicate
            self.assertFalse(
                is_duplicate_lens_run(log, self._rec(session="s2", ts="2026-08-04T18:06:16Z"))
            )

    def test_untagged_falls_back_to_ts_window(self):
        from lens_lib.log import append_record, is_duplicate_lens_run

        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(log, self._rec(session=None))
            self.assertTrue(
                is_duplicate_lens_run(log, self._rec(session=None, ts="2026-08-04T18:06:16Z"))
            )
            self.assertFalse(
                is_duplicate_lens_run(log, self._rec(session=None, ts="2026-08-04T18:30:00Z"))
            )

    def test_mixed_tagged_untagged_is_not_duplicate(self):
        """Window fallback only when BOTH sides are untagged. Mixed must not
        drop a legitimate terminal run for another (or first-tagged) session."""
        from lens_lib.log import append_record, is_duplicate_lens_run

        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(log, self._rec(session=None))
            self.assertFalse(
                is_duplicate_lens_run(
                    log, self._rec(session="other", ts="2026-08-04T18:06:00Z")
                ),
                "untagged then tagged other session must append",
            )
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(log, self._rec(session="s1"))
            self.assertFalse(
                is_duplicate_lens_run(
                    log, self._rec(session=None, ts="2026-08-04T18:06:00Z")
                ),
                "tagged then untagged must append",
            )

    def test_append_run_cli_skips_duplicate(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            lens = Path(td) / "lens.md"
            lens.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log), lenses={"review": str(lens)}, default_lens="review"
                )
                from lens_lib.__main__ import main

                def rec(ts):
                    return json.dumps({
                        "ts": ts, "lens": "review", "deliverable": "d", "rounds": 7,
                        "verdict": "pass", "findings": [], "escalations": [],
                    })

                self.assertEqual(main(["append-run", "--host", "claude-code",
                                       "--session", "s1", "--json", rec("2026-08-04T18:05:25Z")]), 0)
                self.assertEqual(main(["append-run", "--host", "claude-code",
                                       "--session", "s1", "--json", rec("2026-08-04T18:06:16Z")]), 0)
                with open(log) as f:
                    runs = [json.loads(l) for l in f if json.loads(l).get("event") == "lens_run"]
                self.assertEqual(len(runs), 1, "identical re-append should be skipped")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_append_launcher_runs_bare_python3_no_pythonpath(self):
        """The append launcher self-bootstraps sys.path, so a background subagent
        can invoke it as `python3 <path>` with NO leading PYTHONPATH= and from any
        cwd — the pre-grantable form (must-fix 1)."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            (home / ".lens").mkdir(parents=True)
            lens = Path(td) / "review.md"
            lens.write_text(SAMPLE)
            log = home / ".lens" / "runs.jsonl"
            (home / ".lens" / "config.json").write_text(
                json.dumps(
                    {
                        "log_path": str(log),
                        "lenses": {"review": str(lens)},
                        "default_lens": "review",
                    }
                )
            )
            launcher = ROOT / "python" / "lens_append.py"
            record = json.dumps(
                {
                    "ts": "2026-08-05T05:20:00Z", "lens": "review",
                    "deliverable": "launcher-smoke", "rounds": 1, "verdict": "pass",
                    "host": "claude-code", "session": "s1",
                    "findings": [], "escalations": [],
                }
            )
            env = {
                k: v for k, v in os.environ.items() if k != "PYTHONPATH"
            }
            env["HOME"] = str(home)
            env.pop("LENS_LOG_PATH", None)
            # run from a foreign cwd (td), not the repo — proves cwd-independence
            proc = subprocess.run(
                [
                    sys.executable, str(launcher),
                    "--host", "claude-code", "--session", "s1", "--json", record,
                ],
                cwd=str(td), env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("PYTHONPATH", env)
            runs = [
                json.loads(l) for l in log.read_text().splitlines()
                if json.loads(l).get("event") == "lens_run"
            ]
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["deliverable"], "launcher-smoke")
            self.assertEqual(runs[0]["session"], "s1")


class ClaudePermissionsTests(unittest.TestCase):
    """The claude-code analog of the Cursor sandbox: pre-grant the runner's
    out-of-workspace Read + append Bash so a background subagent needn't prompt."""

    def test_grants_lens_read_and_append_idempotently(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            home = Path(td) / "home"
            home.mkdir()
            lensdir = Path(td) / "lenses"
            lensdir.mkdir()
            lens = lensdir / "yusuke.md"
            lens.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log), lenses={"yusuke": str(lens)}, default_lens="yusuke"
                )
                from lens_lib.claude_perms import (
                    ensure_allow,
                    missing_allow,
                    required_allow,
                    settings_path,
                )

                cfg = resolve_config()
                req = required_allow(cfg)
                self.assertIn("Read(~/.lens/**)", req)
                # the append grant is a bare `python3 <path>` (no PYTHONPATH=),
                # emitted in both the literal-${CLAUDE_PLUGIN_ROOT} form (pre-
                # expansion match) and a resolved-absolute form (post-expansion).
                self.assertFalse(any("PYTHONPATH=" in e for e in req))
                self.assertTrue(
                    any("${CLAUDE_PLUGIN_ROOT}/python/lens_append.py" in e for e in req)
                )
                self.assertTrue(
                    any(
                        "lens_append.py" in e and "${CLAUDE_PLUGIN_ROOT}" not in e
                        for e in req
                    )
                )
                self.assertTrue(any("lenses" in e and e.startswith("Read(") for e in req))
                # before the fix every grant is missing
                self.assertEqual(missing_allow(cfg), req)
                path, changed = ensure_allow(cfg)
                self.assertTrue(changed)
                self.assertEqual(path, settings_path())
                self.assertEqual(missing_allow(cfg), [])
                # idempotent
                _, changed2 = ensure_allow(cfg)
                self.assertFalse(changed2)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_preserves_existing_allow(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            home = Path(td) / "home"
            (home / ".claude").mkdir(parents=True)
            (home / ".claude" / "settings.json").write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": ["mcp__agent-deck__*"],
                            "defaultMode": "auto",
                        }
                    }
                )
            )
            lens = Path(td) / "yusuke.md"
            lens.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log), lenses={"yusuke": str(lens)}, default_lens="yusuke"
                )
                from lens_lib.claude_perms import ensure_allow, settings_path

                cfg = resolve_config()
                ensure_allow(cfg)
                with open(settings_path()) as f:
                    data = json.load(f)
                self.assertIn("mcp__agent-deck__*", data["permissions"]["allow"])
                self.assertEqual(data["permissions"].get("defaultMode"), "auto")
                self.assertIn("Read(~/.lens/**)", data["permissions"]["allow"])
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_corrupt_settings_refuses_overwrite(self):
        """A present-but-unparseable settings.json is user data — the doctor
        fix must refuse to write rather than clobber it with only lens grants."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            home = Path(td) / "home"
            (home / ".claude").mkdir(parents=True)
            corrupt = home / ".claude" / "settings.json"
            corrupt.write_text('{"permissions": {"allow": ["keep-me"]', encoding="utf-8")
            lens = Path(td) / "yusuke.md"
            lens.write_text(SAMPLE)
            log = Path(td) / "runs.jsonl"
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                write_config(
                    str(log), lenses={"yusuke": str(lens)}, default_lens="yusuke"
                )
                from lens_lib.claude_perms import (
                    ClaudePermsError,
                    ensure_allow,
                    missing_allow,
                )

                cfg = resolve_config()
                with self.assertRaises(ClaudePermsError):
                    missing_allow(cfg)
                with self.assertRaises(ClaudePermsError):
                    ensure_allow(cfg)
                # the corrupt file is untouched, not overwritten
                self.assertEqual(
                    corrupt.read_text(encoding="utf-8"),
                    '{"permissions": {"allow": ["keep-me"]',
                )
                # and the doctor check surfaces the failure instead of passing
                from lens_lib.doctor import run_doctor

                report = run_doctor(fix_sandbox=False)
                cp = [c for c in report.checks if c.name == "claude_permissions"]
                self.assertTrue(cp and not cp[0].ok)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class IgnoreGlobsTests(unittest.TestCase):
    def test_filter_watched_excludes_ignore_matches(self):
        cwd = str(ROOT)
        keep = str(ROOT / "docs" / "SPEC.md")
        drop = str(ROOT / "CHANGELOG.md")
        watched, excluded = filter_watched(
            [keep, drop], ["**/*.md"], cwd, ignore_globs=["CHANGELOG.md"]
        )
        self.assertEqual(watched, [keep])
        self.assertEqual(excluded, 1)

    def test_builtin_ignores_node_modules(self):
        cwd = str(ROOT)
        nm = str(ROOT / "node_modules" / "pkg" / "readme.md")
        from lens_lib.paths import BUILTIN_IGNORE_GLOBS

        watched, _ = filter_watched(
            [nm], ["**/*.md"], cwd, ignore_globs=list(BUILTIN_IGNORE_GLOBS)
        )
        self.assertEqual(watched, [])

    def test_load_lensignore_walks_up(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".lensignore").write_text(
                "# routine\nCHANGELOG.md\ndocs/**\n", encoding="utf-8"
            )
            sub = Path(td) / "a" / "b"
            sub.mkdir(parents=True)
            self.assertEqual(load_lensignore(str(sub)), ["CHANGELOG.md", "docs/**"])

    def test_run_check_ignores_lensignored_write(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            lens = Path(td) / "lens.md"
            log = Path(td) / "runs.jsonl"
            lens.write_text(SAMPLE)
            home = Path(td) / "home"
            home.mkdir()
            (Path(td) / ".lensignore").write_text("CHANGELOG.md\n", encoding="utf-8")
            changelog = Path(td) / "CHANGELOG.md"
            changelog.write_text("x", encoding="utf-8")
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
                    json.dumps({"type": "user", "timestamp": "2026-07-31T10:00:00.000Z", "cwd": str(td)})
                    + "\n"
                    + json.dumps({
                        "type": "assistant",
                        "timestamp": "2026-07-31T10:00:01.000Z",
                        "message": {"content": [{
                            "type": "tool_use", "name": "Write",
                            "input": {"file_path": str(changelog), "content": "x"},
                        }]},
                    })
                    + "\n"
                )
                result = run_check(
                    host="claude-code", transcript_path=str(transcript),
                    session_id="sess", cwd=td,
                )
                # CHANGELOG.md is ignored → no watched write → no block.
                self.assertFalse(result.watched_writes)
                self.assertFalse(result.blocked)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class AttributionTests(unittest.TestCase):
    def test_armed_session_ids_excludes_stale_arm(self):
        """A stale arm (older than TTL) is not credited — matches the block path."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                arm_session("fresh-sess")
                arm_session("stale-sess", ts="2020-01-01T00:00:00Z")
                ids = armed_session_ids()
                self.assertIn("fresh-sess", ids)
                self.assertNotIn("stale-sess", ids)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_append_run_credits_all_live_arms_lens_agnostic(self):
        """Pinned behavior: a review credits every live-armed session, regardless
        of which lens each asked for. Harmless on a single-user sequential machine;
        with concurrent chats armed for different lenses it is a documented
        loosening (see cmd_append_run / armed_session_ids)."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            log = Path(td) / "runs.jsonl"
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                lens = Path(td) / "lens.md"
                lens.write_text(SAMPLE)
                write_config(
                    str(log), lenses={"review": str(lens)},
                    default_lens="review", enforce=True,
                )
                arm_session("sess-deck")
                arm_session("sess-yusuke")
                record = json.dumps({
                    "ts": "2026-07-31T10:00:02.000Z", "lens": "yusuke",
                    "deliverable": "doc", "rounds": 1, "verdict": "pass",
                    "findings": [], "escalations": [],
                })
                out = subprocess.run(
                    [sys.executable, "-m", "lens_lib", "append-run",
                     "--json", record, "--session", "subagent"],
                    cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
                    capture_output=True, text=True,
                )
                self.assertEqual(out.returncode, 0, out.stderr)
                # Both arms are credited even though the run's lens is "yusuke".
                self.assertTrue(has_lens_run_for_sessions(log, ["sess-deck"]))
                self.assertTrue(has_lens_run_for_sessions(log, ["sess-yusuke"]))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_append_run_credits_armed_session(self):
        """A review logged under a sub-agent session credits the armed parent."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            log = Path(td) / "runs.jsonl"
            home = Path(td) / "home"
            home.mkdir()
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            os.environ.pop("LENS_LOG_PATH", None)
            try:
                lens = Path(td) / "lens.md"
                lens.write_text(SAMPLE)
                write_config(
                    str(log), lenses={"review": str(lens)},
                    default_lens="review", enforce=True,
                )
                arm_session("parent-sess")
                self.assertEqual(armed_session_ids(), ["parent-sess"])

                record = json.dumps({
                    "ts": "2026-07-31T10:00:02.000Z", "lens": "review",
                    "deliverable": "doc", "rounds": 1, "verdict": "pass",
                    "findings": [], "escalations": [],
                })
                out = subprocess.run(
                    [sys.executable, "-m", "lens_lib", "append-run",
                     "--json", record, "--session", "subagent-sess"],
                    cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
                    capture_output=True, text=True,
                )
                self.assertEqual(out.returncode, 0, out.stderr)
                # The run is tagged with the sub-agent session AND credits the
                # armed parent, so the parent's gate is satisfied.
                self.assertTrue(has_lens_run_for_sessions(log, ["parent-sess"]))
                self.assertTrue(has_lens_run_for_sessions(log, ["subagent-sess"]))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class FindingShapeTests(unittest.TestCase):
    """Optional class on findings — contract + append validator (F2.5)."""

    def _record(self, findings):
        return {
            "ts": "2026-08-17T00:00:00Z",
            "event": "lens_run",
            "lens": "review",
            "deliverable": "d",
            "rounds": 1,
            "verdict": "pass",
            "findings": findings,
            "escalations": [],
        }

    def test_finding_with_and_without_class(self):
        from lens_lib.log import validate_lens_run_shape

        base = {
            "round": 1,
            "check": "source-grounded",
            "target": "t",
            "severity": "FIX",
            "reaction": "fixed",
        }
        self.assertEqual(validate_lens_run_shape(self._record([base])), [])
        with_class = {**base, "class": "fragile-line-cites", "note": "n"}
        self.assertEqual(validate_lens_run_shape(self._record([with_class])), [])

    def test_rejects_unknown_finding_key(self):
        from lens_lib.log import validate_lens_run_shape

        finding = {
            "round": 1,
            "check": "x",
            "target": "t",
            "severity": "FIX",
            "reaction": "fixed",
            "extra": "nope",
        }
        errors = validate_lens_run_shape(self._record([finding]))
        self.assertTrue(any("unknown keys" in e for e in errors))

    def test_rejects_bad_class_pattern(self):
        from lens_lib.log import validate_lens_run_shape

        finding = {
            "round": 1,
            "check": "x",
            "target": "t",
            "severity": "FIX",
            "reaction": "fixed",
            "class": "Bad Class",
        }
        errors = validate_lens_run_shape(self._record([finding]))
        self.assertTrue(any("bad class label" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
