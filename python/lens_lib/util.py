"""Shared helpers."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    """System-clock UTC timestamp (never model-estimated).

    Millisecond resolution so a lens_run and a back-to-back side-channel write
    in the same wall-clock second still order deterministically (NOT-40).
    """
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def expand_path(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def claude_home() -> Path:
    return expand_path("~/.claude")


def cursor_home() -> Path:
    return expand_path("~/.cursor")


def codex_home() -> Path:
    return expand_path("~/.codex")


def lens_config_path() -> Path:
    return expand_path("~/.lens/config.json")


def correction_signals_path() -> Path:
    return expand_path("~/.lens/correction_signals.jsonl")


def lens_patches_path() -> Path:
    return expand_path("~/.lens/lens_patches.jsonl")


def system_temp_dir() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def classic_temp_dirs() -> tuple[Path, ...]:
    """Classic Unix scratch dirs (`/tmp`, `/private/tmp`).

    `$TMPDIR` (system_temp_dir) is `/var/folders/.../T` on macOS, but agent
    harnesses stash session scratch under `/tmp` — e.g. Claude Code writes
    `/private/tmp/claude-<uid>/…/scratchpad/*.md`. Those are never deliverables.
    """
    return tuple(dict.fromkeys(Path(c).resolve() for c in ("/tmp", "/private/tmp")))


def _workspace_key(workspace_root: str) -> str:
    return hashlib.sha256(str(Path(workspace_root).resolve()).encode("utf-8")).hexdigest()[
        :16
    ]


def _safe_session(session: str) -> str:
    """Filesystem-safe path segment for a session/conversation id."""
    return session.replace("/", "_").replace("\\", "_")


def sessions_root() -> Path:
    """Root dir holding per-session marker files (writes.txt / armed.txt)."""
    return expand_path("~/.lens/sessions")


def session_writes_path(session: str) -> Path:
    """Cursor afterFileEdit side-channel keyed by conversation/session id."""
    return sessions_root() / _safe_session(session) / "writes.txt"


def session_armed_path(session: str) -> Path:
    """Explicit-invocation arm marker keyed by session id (F3.5)."""
    return sessions_root() / _safe_session(session) / "armed.txt"


def conversation_workspace_writes_path(workspace_root: str, conversation_id: str) -> Path:
    """Primary Cursor side-channel: (workspace, conversation_id)."""
    key = _workspace_key(workspace_root)
    safe = _safe_session(conversation_id)
    return (
        sessions_root()
        / "by-workspace"
        / key
        / "conversations"
        / safe
        / "writes.txt"
    )


def workspace_writes_path(workspace_root: str) -> Path:
    """Fallback when conversation/session id is missing (I-3)."""
    key = _workspace_key(workspace_root)
    return sessions_root() / "by-workspace" / key / "writes.txt"


def prefer_conversation_ids(
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    *extra: Optional[str],
) -> list:
    """Order ids with conversation_id first for analysis / primary keying."""
    ordered = []
    for val in (conversation_id, session_id) + extra:
        if val and str(val) not in ordered:
            ordered.append(str(val))
    return ordered


INVOCATION_TEMPLATE = (
    "Invoke the `lens` agent with: "
    "lens=<configured name, or omit for default_lens>, "
    "round=<n>, deliverable=\"<stable key>\", files=[...], sources=[...], "
    "hold_policy=wait-for-go|auto-apply (omit = auto-apply), "
    "and on rounds after the first: prior_findings + your reaction per finding. "
    "Reuse the same deliverable key every round."
)

SKIP_TEMPLATE = (
    "run `PYTHONPATH=<plugin-root>/python python3 -m lens_lib skip "
    "\"<deliverable>\" --session <the session id shown above> "
    "[--reason \"<why held>\"]` — only when the owner explicitly said to hold; "
    "it logs a lens_skip and clears the loop for that deliverable."
)

CURSOR_UNLOCK_HINT = (
    "To unlock without a lens run: set \"enforce\": false in ~/.lens/config.json "
    "(re-enable when ready), or close the Agent chat. "
    "Preferred: invoke the `lens` agent so a lens_run is logged."
)

CURSOR_LOOP_LIMIT_DEFAULT = 5
