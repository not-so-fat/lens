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
from lens_lib.log import (  # noqa: E402
    append_record,
    has_lens_run_since,
    latest_gate_ts,
    latest_lens_run_ts,
    latest_lens_skip_ts,
    parse_iso_ts,
)
from lens_lib.paths import (  # noqa: E402
    filter_watched,
    load_lensignore,
    matches_glob,
    path_matches_watch,
)
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

    def test_harness_scratch_is_excluded(self):
        from lens_lib.paths import filter_watched, is_excluded

        # Claude Code stashes session scratch under /private/tmp/claude-<uid>/ —
        # markdown drafts there (PR bodies, etc.) are never deliverables.
        scratch = "/private/tmp/claude-501/x/scratchpad/pr-body-1.md"
        tmp_md = "/tmp/pr.md"
        self.assertTrue(is_excluded(Path(scratch)))
        self.assertTrue(is_excluded(Path(tmp_md)))
        # A real repo deliverable is still watched.
        watched, _ = filter_watched(
            [scratch, tmp_md, "/Users/x/repo/docs/SPEC.md"], ["**/*.md"], "/Users/x/repo"
        )
        self.assertEqual(watched, ["/Users/x/repo/docs/SPEC.md"])


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

    def test_held_verdict_and_pending_owner_reaction(self):
        from lens_lib.log import validate_lens_run_shape

        record = self._record(
            [
                {
                    "round": 1,
                    "check": "source-grounded",
                    "target": "§2",
                    "severity": "FIX",
                    "reaction": "pending-owner",
                    "note": "awaiting owner go",
                }
            ]
        )
        record["verdict"] = "held"
        self.assertEqual(validate_lens_run_shape(record), [])

    def test_rejects_bad_reaction(self):
        from lens_lib.log import validate_lens_run_shape

        finding = {
            "round": 1,
            "check": "x",
            "target": "t",
            "severity": "FIX",
            "reaction": "waiting",
        }
        errors = validate_lens_run_shape(self._record([finding]))
        self.assertTrue(any("reaction must be" in e for e in errors))


class LensInvocationDetectionTests(unittest.TestCase):
    """F3.5: detect an explicit 'use the lens' request without misfiring."""

    def test_positive_phrasings(self):
        from lens_lib.check import is_lens_invocation

        for p in (
            "run the lens on this",
            "use the lens please",
            "use the yusuke lens",
            "with deck lens review the doc",
            "lens=yusuke round=1",
            "apply the lens",
            "run the lens loop",
            "invoke the yusuke lens now",  # words ending in "nt" nearby must still arm
        ):
            self.assertTrue(is_lens_invocation(p, ["yusuke", "deck"]), p)

    def test_negative_phrasings(self):
        from lens_lib.check import is_lens_invocation

        for p in (
            "don't use the lens",
            "without using the lens",
            "no need to run the lens",
            "skip the lens this time",
            "use my eyeglasses lens metaphor",
            "read the lens documentation",
            "run lens doctor",
            "run lens-close",
        ):
            self.assertFalse(is_lens_invocation(p, ["yusuke", "deck"]), p)

    def test_fenced_transcript_content_does_not_arm(self):
        from lens_lib.check import is_lens_invocation

        prompt = (
            "Summarize this session.\n"
            "=== BEGIN SESSION TRANSCRIPT ===\n"
            "assistant: Invoke the `lens` agent with lens=yusuke ...\n"
            "Lens enforcement: run the lens now\n"
            "=== END SESSION TRANSCRIPT ===\n"
        )
        self.assertFalse(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_live_invocation_outside_fence_still_arms(self):
        from lens_lib.check import is_lens_invocation

        prompt = (
            "use the yusuke lens on the result below\n"
            "=== BEGIN SESSION TRANSCRIPT ===\n"
            "assistant: blah\n"
            "=== END SESSION TRANSCRIPT ===\n"
        )
        self.assertTrue(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_task_notification_does_not_arm(self):
        from lens_lib.check import is_lens_invocation

        prompt = (
            "<task-notification>Lens round 3 agent: complete this lens review"
            "</task-notification>"
        )
        self.assertFalse(is_lens_invocation(prompt, ["yusuke", "deck"]), prompt[:80])

    def test_non_string_prompt_is_safe(self):
        from lens_lib.check import is_lens_invocation

        self.assertFalse(is_lens_invocation(None, ["yusuke"]))
        self.assertFalse(is_lens_invocation(["use", "lens"], ["yusuke"]))


class LatestGateTsTests(unittest.TestCase):
    def test_latest_gate_ts_prefers_later_run_or_skip(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "runs.jsonl"
            append_record(
                log,
                {
                    "ts": "2026-08-27T06:00:00Z",
                    "event": "lens_run",
                    "session": "s1",
                    "lens": "review",
                    "deliverable": "a",
                    "rounds": 1,
                    "verdict": "pass",
                    "findings": [],
                    "escalations": [],
                },
            )
            append_record(
                log,
                {
                    "ts": "2026-08-27T07:00:00Z",
                    "event": "lens_skip",
                    "session": "s1",
                    "deliverable": "b",
                },
            )
            self.assertEqual(
                latest_gate_ts(log, ["s1"]),
                "2026-08-27T07:00:00Z",
            )
            self.assertEqual(
                latest_lens_run_ts(log, ["s1"]),
                "2026-08-27T06:00:00Z",
            )
            self.assertEqual(
                latest_lens_skip_ts(log, ["s1"]),
                "2026-08-27T07:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
