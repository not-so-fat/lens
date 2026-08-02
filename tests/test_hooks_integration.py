#!/usr/bin/env python3
"""Integration tests: spawn host hook entry points as subprocesses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
sys.path.insert(0, str(PYTHON))
from lens_lib.util import utc_now_iso  # noqa: E402
CLAUDE_STOP = PYTHON / "claude_stop.py"
CLAUDE_PROMPT = PYTHON / "claude_user_prompt.py"
CURSOR_STOP = PYTHON / "cursor_stop.py"
CURSOR_EDIT = PYTHON / "cursor_after_file_edit.py"

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


def _write_config(home: Path, lens: Path, log: Path, enforce: bool = True) -> None:
    cfg_dir = home / ".lens"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(
            {
                "lenses": {"review": str(lens)},
                "default_lens": "review",
                "log_path": str(log),
                "enforce": enforce,
                "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_hook(script: Path, payload: dict, env: dict, cwd: Optional[Path] = None):
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return proc


class HookIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(dir=str(ROOT))
        self.td = Path(self._td.name)
        self.home = self.td / "home"
        self.home.mkdir()
        self.lens = self.td / "review.md"
        self.lens.write_text(SAMPLE, encoding="utf-8")
        self.log = self.td / "runs.jsonl"
        self.deliverable = self.td / "out.md"
        self.deliverable.write_text("hello", encoding="utf-8")
        _write_config(self.home, self.lens, self.log, enforce=True)
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env.pop("LENS_LOG_PATH", None)
        self.env.pop("LENS_DEFAULT", None)
        self.env.pop("LENS_PATH", None)

    def tearDown(self):
        self._td.cleanup()

    def _transcript_with_write(self) -> Path:
        t = self.td / "sess.jsonl"
        t.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-08-01T10:00:00.000Z",
                    "cwd": str(self.td),
                    "sessionId": "sess-1",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-08-01T10:00:01.000Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {
                                    "file_path": str(self.deliverable),
                                    "content": "x",
                                },
                            }
                        ]
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return t

    def test_claude_stop_blocks_without_lens_run(self):
        transcript = self._transcript_with_write()
        proc = _run_hook(
            CLAUDE_STOP,
            {
                "transcript_path": str(transcript),
                "session_id": "sess-1",
                "cwd": str(self.td),
            },
            self.env,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("Invoke the `lens` agent", proc.stderr)
        # hook_check appended
        lines = self.log.read_text(encoding="utf-8").strip().splitlines()
        self.assertTrue(lines)
        rec = json.loads(lines[-1])
        self.assertEqual(rec["event"], "hook_check")
        self.assertEqual(rec["host"], "claude-code")
        self.assertTrue(rec["blocked"])
        self.assertTrue(rec["watched_writes"])
        self.assertFalse(rec["lens_run_found"])

    def test_claude_stop_passes_with_lens_run(self):
        transcript = self._transcript_with_write()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-08-01T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "out",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "session": "sess-1",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        proc = _run_hook(
            CLAUDE_STOP,
            {
                "transcript_path": str(transcript),
                "session_id": "sess-1",
                "cwd": str(self.td),
            },
            self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertFalse(rec["blocked"])
        self.assertTrue(rec["lens_run_found"])

    def test_claude_stop_no_watched_writes_passes(self):
        t = self.td / "empty.jsonl"
        t.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-08-01T10:00:00.000Z",
                    "cwd": str(self.td),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        proc = _run_hook(
            CLAUDE_STOP,
            {"transcript_path": str(t), "session_id": "s", "cwd": str(self.td)},
            self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_claude_newer_other_session_run_does_not_leak(self):
        """I-8: Claude gate is session-scoped — another session's run must not clear this one."""
        transcript = self._transcript_with_write()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-08-01T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "other",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "session": "other-sess",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        proc = _run_hook(
            CLAUDE_STOP,
            {
                "transcript_path": str(transcript),
                "session_id": "sess-1",
                "cwd": str(self.td),
            },
            self.env,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(rec["blocked"])
        self.assertEqual(rec.get("gate"), "none")

    def test_claude_untagged_lens_run_still_satisfies(self):
        """Bash-appended Claude runs may omit session — forgive if in time window."""
        transcript = self._transcript_with_write()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-08-01T10:00:02.000Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "out",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        proc = _run_hook(
            CLAUDE_STOP,
            {
                "transcript_path": str(transcript),
                "session_id": "sess-1",
                "cwd": str(self.td),
            },
            self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertFalse(rec["blocked"])
        self.assertTrue(rec["lens_run_found"])

    def _transcript_no_write(self, name: str = "chat.jsonl", sid: str = "sess-1") -> Path:
        t = self.td / name
        t.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-08-01T10:00:00.000Z",
                    "cwd": str(self.td),
                    "sessionId": sid,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return t

    def test_claude_explicit_invocation_arms_and_blocks_without_writes(self):
        """I-9: 'use <lens>' on a chat turn (no watched write) must still enforce a lens_run."""
        prompt = _run_hook(
            CLAUDE_PROMPT,
            {"prompt": "use yusuke lens on this", "session_id": "sess-1", "cwd": str(self.td)},
            self.env,
        )
        self.assertEqual(prompt.returncode, 0, prompt.stderr)
        transcript = self._transcript_no_write()
        stop = _run_hook(
            CLAUDE_STOP,
            {"transcript_path": str(transcript), "session_id": "sess-1", "cwd": str(self.td)},
            self.env,
        )
        self.assertEqual(stop.returncode, 2, stop.stderr)  # blocked despite no writes
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(rec["armed"])
        self.assertTrue(rec["blocked"])
        self.assertFalse(rec["wrote_watched"])
        # A session-tagged lens_run satisfies the arm; the next stop passes and disarms.
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now_iso(),
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "chat-answer",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "claude-code",
                        "session": "sess-1",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        stop2 = _run_hook(
            CLAUDE_STOP,
            {"transcript_path": str(transcript), "session_id": "sess-1", "cwd": str(self.td)},
            self.env,
        )
        self.assertEqual(stop2.returncode, 0, stop2.stderr)

    def test_claude_non_lens_prompt_does_not_arm(self):
        """A normal prompt must not arm — no false blocks on chat turns."""
        _run_hook(
            CLAUDE_PROMPT,
            {"prompt": "compare two companies and summarize", "session_id": "sess-2", "cwd": str(self.td)},
            self.env,
        )
        transcript = self._transcript_no_write("chat2.jsonl", "sess-2")
        stop = _run_hook(
            CLAUDE_STOP,
            {"transcript_path": str(transcript), "session_id": "sess-2", "cwd": str(self.td)},
            self.env,
        )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertFalse(rec["armed"])
        self.assertFalse(rec["blocked"])

    def test_cursor_after_file_edit_then_stop_blocks(self):
        """Cursor stop often has little transcript — sidechannel is the critical path."""
        edit = _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "conversation_id": "conv-cursor-1",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        self.assertEqual(edit.returncode, 0, edit.stderr)
        self.assertEqual(json.loads(edit.stdout or "{}"), {})

        # No transcript_path — mirrors Cursor stop docs' thin payload
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "loop_count": 0,
                "conversation_id": "conv-cursor-1",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        out = json.loads(stop.stdout)
        self.assertIn("followup_message", out)
        self.assertIn("Invoke the `lens` agent", out["followup_message"])
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(rec["host"], "cursor")
        self.assertTrue(rec["blocked"])
        self.assertTrue(rec["watched_writes"])

    def test_cursor_edit_conversation_id_stop_session_id_same_value(self):
        """Field-name fan-out: edit records conversation_id; stop only sends session_id."""
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "conversation_id": "same-id",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "session_id": "same-id",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        out = json.loads(stop.stdout)
        self.assertIn("followup_message", out)

    def test_cursor_stop_passes_after_lens_run(self):
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "session_id": "conv-2",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        # ts after the stamped side-channel write so the time window admits it
        time.sleep(1.05)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now_iso(),
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "out",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "cursor",
                        "session": "conv-2",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "session_id": "conv-2",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        out = json.loads(stop.stdout)
        self.assertNotIn("followup_message", out)

    def test_cursor_stale_lens_run_does_not_unblock_fresh_conversation(self):
        """P1: historical lens_run must not satisfy a new chat with no transcript."""
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2020-01-01T00:00:00Z",
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "ancient",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "cursor",
                        "session": "other-chat",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "conversation_id": "fresh-chat",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "conversation_id": "fresh-chat",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        out = json.loads(stop.stdout)
        self.assertIn("followup_message", out)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(rec["watched_writes"])
        self.assertFalse(rec["lens_run_found"])
        self.assertTrue(rec["blocked"])

    def test_cursor_newer_other_session_run_does_not_leak(self):
        """Cursor must not use a global time gate — other chat's newer run must not clear this one."""
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "conversation_id": "chat-x",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        time.sleep(1.05)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now_iso(),
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "other",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "cursor",
                        "session": "chat-y",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "conversation_id": "chat-x",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        out = json.loads(stop.stdout)
        self.assertIn("followup_message", out)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(rec["blocked"])
        self.assertEqual(rec.get("gate"), "none")
        self.assertTrue(rec.get("wrote_watched"))

    def test_cursor_second_write_after_lens_run_still_enforces(self):
        """I-7 light: writes after a session lens_run still require a new review."""
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "conversation_id": "multi",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        time.sleep(1.05)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now_iso(),
                        "event": "lens_run",
                        "lens": "review",
                        "deliverable": "first",
                        "rounds": 1,
                        "verdict": "pass",
                        "host": "cursor",
                        "session": "multi",
                        "findings": [],
                        "escalations": [],
                    }
                )
                + "\n"
            )
        stop1 = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "conversation_id": "multi",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        self.assertNotIn("followup_message", json.loads(stop1.stdout))
        time.sleep(1.05)
        other = self.td / "second.md"
        other.write_text("y", encoding="utf-8")
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(other),
                "conversation_id": "multi",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop2 = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "conversation_id": "multi",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        out = json.loads(stop2.stdout)
        self.assertIn("followup_message", out)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(rec["blocked"])
        self.assertFalse(rec["lens_run_found"])

    def test_cursor_enforce_false_no_followup(self):
        _write_config(self.home, self.lens, self.log, enforce=False)
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "session_id": "conv-3",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "session_id": "conv-3",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        out = json.loads(stop.stdout)
        self.assertNotIn("followup_message", out)
        rec = json.loads(self.log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertFalse(rec["blocked"])
        self.assertTrue(rec["watched_writes"])

    def test_hook_scripts_exist_for_manifest_commands(self):
        claude_hooks = json.loads((ROOT / "hooks" / "claude-hooks.json").read_text())
        cursor_hooks = json.loads((ROOT / "hooks" / "cursor-hooks.json").read_text())
        self.assertIn("Stop", claude_hooks["hooks"])
        self.assertTrue(CLAUDE_STOP.is_file())
        self.assertTrue(CURSOR_STOP.is_file())
        self.assertTrue(CURSOR_EDIT.is_file())
        stop_cmd = cursor_hooks["hooks"]["stop"][0]["command"]
        self.assertIn("cursor_stop.py", stop_cmd)
        self.assertIn("${CURSOR_PLUGIN_ROOT}", stop_cmd)
        edit_cmd = cursor_hooks["hooks"]["afterFileEdit"][0]["command"]
        self.assertIn("${CURSOR_PLUGIN_ROOT}", edit_cmd)
        self.assertEqual(cursor_hooks["hooks"]["stop"][0].get("loop_limit"), 5)
        claude_cmd = json.dumps(claude_hooks)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", claude_cmd)

    def test_cursor_last_followup_includes_unlock_hint(self):
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "session_id": "conv-limit",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "session_id": "conv-limit",
                "workspace_roots": [str(self.td)],
                "loop_count": 4,
                "loop_limit": 5,
            },
            self.env,
        )
        out = json.loads(stop.stdout)
        self.assertIn("followup_message", out)
        self.assertIn("LAST FORCED FOLLOW-UP", out["followup_message"])
        self.assertIn("enforce", out["followup_message"])

    def test_cursor_loop_limit_exhausted_no_followup(self):
        _run_hook(
            CURSOR_EDIT,
            {
                "file_path": str(self.deliverable),
                "session_id": "conv-exhausted",
                "workspace_roots": [str(self.td)],
            },
            self.env,
        )
        stop = _run_hook(
            CURSOR_STOP,
            {
                "status": "completed",
                "session_id": "conv-exhausted",
                "workspace_roots": [str(self.td)],
                "loop_count": 5,
                "loop_limit": 5,
            },
            self.env,
        )
        out = json.loads(stop.stdout)
        self.assertNotIn("followup_message", out)
        self.assertIn("loop_limit", stop.stderr)
        lines = self.log.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(ln)["event"] for ln in lines]
        self.assertIn("hook_limit_exhausted", events)


class CursorSessionIdMismatchTests(unittest.TestCase):
    """Session-id divergence between afterFileEdit and stop."""

    def _env(self, td: Path):
        home = td / "home"
        home.mkdir()
        lens = td / "review.md"
        lens.write_text(SAMPLE)
        log = td / "runs.jsonl"
        deliverable = td / "out.md"
        deliverable.write_text("x")
        _write_config(home, lens, log)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env.pop("LENS_LOG_PATH", None)
        return env, deliverable, log

    def test_mismatched_ids_do_not_cross_talk_via_workspace(self):
        """I-3: (workspace, conversation_id) is primary — chat A writes must not block B."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            env, deliverable, _log = self._env(td)
            _run_hook(
                CURSOR_EDIT,
                {
                    "file_path": str(deliverable),
                    "conversation_id": "A",
                    "workspace_roots": [str(td)],
                },
                env,
            )
            stop = _run_hook(
                CURSOR_STOP,
                {
                    "status": "completed",
                    "conversation_id": "B",
                    "workspace_roots": [str(td)],
                },
                env,
            )
            out = json.loads(stop.stdout)
            self.assertNotIn("followup_message", out)

    def test_missing_ids_fall_back_to_workspace_sidechannel(self):
        """I-3: workspace-wide fallback only when conversation/session id is absent."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            env, deliverable, log = self._env(td)
            _run_hook(
                CURSOR_EDIT,
                {
                    "file_path": str(deliverable),
                    "workspace_roots": [str(td)],
                },
                env,
            )
            stop = _run_hook(
                CURSOR_STOP,
                {
                    "status": "completed",
                    "workspace_roots": [str(td)],
                },
                env,
            )
            out = json.loads(stop.stdout)
            self.assertIn("followup_message", out)
            rec = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
            self.assertTrue(rec["blocked"])

    def test_mismatched_ids_without_workspace_root_still_miss(self):
        """I-1 residual: no workspace on edit + different ids → silent pass."""
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td_s:
            td = Path(td_s)
            env, deliverable, _log = self._env(td)
            edit = _run_hook(
                CURSOR_EDIT,
                {"file_path": str(deliverable), "conversation_id": "A"},
                env,
            )
            self.assertIn("no workspace_roots", edit.stderr)
            stop = _run_hook(
                CURSOR_STOP,
                {
                    "status": "completed",
                    "conversation_id": "B",
                    "workspace_roots": [str(td)],
                },
                env,
            )
            out = json.loads(stop.stdout)
            self.assertNotIn("followup_message", out)


if __name__ == "__main__":
    unittest.main()
