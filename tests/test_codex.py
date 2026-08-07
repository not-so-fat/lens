#!/usr/bin/env python3
"""Codex host support tests (F6): write extractor, hooks, install, gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
sys.path.insert(0, str(PYTHON))

from lens_lib.codex_writes import extract_codex_write_paths  # noqa: E402

CODEX_STOP = PYTHON / "codex_stop.py"
CODEX_POST = PYTHON / "codex_post_tool_use.py"
CODEX_PROMPT = PYTHON / "codex_user_prompt.py"

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

PATCH = """*** Begin Patch
*** Update File: {p}
@@
-old
+new
*** End Patch"""


class ExtractorTests(unittest.TestCase):
    def test_apply_patch_update_as_string(self):
        self.assertEqual(
            extract_codex_write_paths("apply_patch", PATCH.format(p="docs/a.md")),
            ["docs/a.md"],
        )

    def test_shell_command_list_wrapping(self):
        payload = {"command": ["apply_patch", PATCH.format(p="/abs/b.md")]}
        self.assertEqual(
            extract_codex_write_paths("shell", payload), ["/abs/b.md"]
        )

    def test_input_key_nesting(self):
        payload = {"input": PATCH.format(p="c.md")}
        self.assertEqual(extract_codex_write_paths("local_shell", payload), ["c.md"])

    def test_add_delete_move_markers(self):
        blob = (
            "*** Begin Patch\n"
            "*** Add File: new.md\n"
            "*** Delete File: gone.md\n"
            "*** Update File: keep.md\n"
            "*** Move to: renamed.md\n"
            "*** End Patch"
        )
        self.assertEqual(
            extract_codex_write_paths("apply_patch", blob),
            ["new.md", "gone.md", "keep.md", "renamed.md"],
        )

    def test_explicit_file_path_field(self):
        self.assertEqual(
            extract_codex_write_paths("edit", {"file_path": "d.md"}), ["d.md"]
        )

    def test_read_only_call_returns_empty(self):
        self.assertEqual(extract_codex_write_paths("shell", {"command": ["cat", "x.md"]}), [])
        self.assertEqual(extract_codex_write_paths("shell", {"command": ["grep", "File:", "x"]}), [])

    def test_dedup_preserves_order(self):
        blob = PATCH.format(p="dup.md") + "\n" + PATCH.format(p="dup.md")
        self.assertEqual(extract_codex_write_paths("apply_patch", blob), ["dup.md"])


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


def _run(script: Path, payload: dict, env: dict, cwd: Optional[Path] = None):
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        check=False,
    )


class CodexGateTests(unittest.TestCase):
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
        _write_config(self.home, self.lens, self.log)
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        for k in ("LENS_LOG_PATH", "LENS_DEFAULT", "LENS_PATH"):
            self.env.pop(k, None)

    def tearDown(self):
        self._td.cleanup()

    def _post_write(self, session="cx-1"):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "shell",
            "tool_input": {"command": ["apply_patch", PATCH.format(p=str(self.deliverable))]},
            "session_id": session,
            "cwd": str(self.td),
        }
        return _run(CODEX_POST, payload, self.env, cwd=self.td)

    def _stop(self, session="cx-1"):
        payload = {"hook_event_name": "Stop", "session_id": session, "cwd": str(self.td)}
        return _run(CODEX_STOP, payload, self.env, cwd=self.td)

    def test_gate_blocks_then_clears(self):
        # 1. record a Codex apply_patch write
        p = self._post_write()
        self.assertEqual(p.returncode, 0, p.stderr)
        # 2. stop blocks — watched write, no lens_run
        s = self._stop()
        out = json.loads(s.stdout or "{}")
        self.assertEqual(out.get("decision"), "block", f"stdout={s.stdout} err={s.stderr}")
        # 3. append a lens_run tagged for this session
        append = PYTHON / "lens_append.py"
        rec = {
            "ts": "2027-01-01T00:00:00Z",  # after the write (reviewer stamps date -u)
            "lens": "review",
            "deliverable": "out.md",
            "rounds": 1,
            "verdict": "pass",
            "findings": [],
            "escalations": [],
        }
        proc = subprocess.run(
            [sys.executable, str(append), "--host", "codex", "--session", "cx-1",
             "--json", json.dumps(rec)],
            text=True, capture_output=True, env=self.env, cwd=str(self.td), check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # 4. stop now passes
        s2 = self._stop()
        out2 = json.loads(s2.stdout or "{}")
        self.assertNotEqual(out2.get("decision"), "block", f"stdout={s2.stdout} err={s2.stderr}")

    def test_unwatched_write_does_not_block(self):
        # a .txt write is not in watch_globs
        other = self.td / "note.txt"
        payload = {
            "tool_name": "apply_patch",
            "tool_input": PATCH.format(p=str(other)),
            "session_id": "cx-2",
            "cwd": str(self.td),
        }
        _run(CODEX_POST, payload, self.env, cwd=self.td)
        s = self._stop(session="cx-2")
        out = json.loads(s.stdout or "{}")
        self.assertNotEqual(out.get("decision"), "block", f"stdout={s.stdout} err={s.stderr}")

    def test_arming_creates_marker(self):
        payload = {"prompt": "use the review lens on this", "session_id": "cx-arm"}
        r = _run(CODEX_PROMPT, payload, self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        armed = self.home / ".lens" / "sessions" / "cx-arm" / "armed.txt"
        self.assertTrue(armed.is_file(), "arming should create the marker file")


class CodexInstallTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(dir=str(ROOT))
        self.td = Path(self._td.name)
        self.home = self.td / "home"
        (self.home / ".codex").mkdir(parents=True)
        self._orig_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self):
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        self._td.cleanup()

    def test_install_renders_absolute_paths_and_merges(self):
        from lens_lib.codex_config import install_agent, install_hooks, codex_hooks_path

        # pre-existing unrelated user hook must survive the merge
        existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo keepme"}]}]}}
        codex_hooks_path().write_text(json.dumps(existing), encoding="utf-8")

        agent_path, _ = install_agent(ROOT)
        self.assertTrue(agent_path.is_file())
        self.assertNotIn("${CODEX_PLUGIN_ROOT}", agent_path.read_text(encoding="utf-8"))
        self.assertIn(str(ROOT), agent_path.read_text(encoding="utf-8"))

        hooks_path, _ = install_hooks(ROOT)
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        cmds = json.dumps(data)
        self.assertIn("codex_stop.py", cmds)
        self.assertIn("codex_post_tool_use.py", cmds)
        self.assertIn("codex_user_prompt.py", cmds)
        self.assertIn("echo keepme", cmds)  # user's hook preserved
        self.assertNotIn("${CODEX_PLUGIN_ROOT}", cmds)

    def test_writable_roots_status_flags_workspace_write_gap(self):
        from lens_lib.codex_config import writable_roots_status
        from lens_lib.config import Config

        (self.home / ".codex" / "config.toml").write_text(
            'sandbox_mode = "workspace-write"\n[sandbox_workspace_write]\nwritable_roots = ["/somewhere/else"]\n',
            encoding="utf-8",
        )
        cfg = Config(
            source="test",
            lenses={},
            lenses_dir=None,
            default_lens="review",
            log_path=str(self.home / ".lens" / "runs.jsonl"),
            enforce=True,
            watch_globs=["**/*.md"],
        )
        ok, detail = writable_roots_status(cfg)
        self.assertFalse(ok, detail)
        self.assertIn("writable_roots", detail)


if __name__ == "__main__":
    unittest.main()
