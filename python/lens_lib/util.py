"""Shared helpers."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    """System-clock UTC timestamp (never model-estimated)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def system_temp_dir() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _workspace_key(workspace_root: str) -> str:
    return hashlib.sha256(str(Path(workspace_root).resolve()).encode("utf-8")).hexdigest()[
        :16
    ]


def _safe_session(session: str) -> str:
    """Filesystem-safe path segment for a session/conversation id."""
    return session.replace("/", "_").replace("\\", "_")


def session_writes_path(session: str) -> Path:
    """Cursor afterFileEdit side-channel keyed by conversation/session id."""
    return expand_path("~/.lens/sessions") / _safe_session(session) / "writes.txt"


def session_armed_path(session: str) -> Path:
    """Explicit-invocation arm marker keyed by session id (I-9)."""
    return expand_path("~/.lens/sessions") / _safe_session(session) / "armed.txt"


def conversation_workspace_writes_path(workspace_root: str, conversation_id: str) -> Path:
    """Primary Cursor side-channel: (workspace, conversation_id)."""
    key = _workspace_key(workspace_root)
    safe = _safe_session(conversation_id)
    return (
        expand_path("~/.lens/sessions")
        / "by-workspace"
        / key
        / "conversations"
        / safe
        / "writes.txt"
    )


def workspace_writes_path(workspace_root: str) -> Path:
    """Fallback when conversation/session id is missing (I-3)."""
    key = _workspace_key(workspace_root)
    return expand_path("~/.lens/sessions") / "by-workspace" / key / "writes.txt"


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
    "and on rounds after the first: prior_findings + your reaction per finding. "
    "Reuse the same deliverable key every round."
)

CURSOR_UNLOCK_HINT = (
    "To unlock without a lens run: set \"enforce\": false in ~/.lens/config.json "
    "(re-enable when ready), or close the Agent chat. "
    "Preferred: invoke the `lens` agent so a lens_run is logged."
)

CURSOR_LOOP_LIMIT_DEFAULT = 5
