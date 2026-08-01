"""Shared helpers."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    """System-clock UTC timestamp (never model-estimated)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expand_path(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def claude_home() -> Path:
    return expand_path("~/.claude")


def cursor_home() -> Path:
    return expand_path("~/.cursor")


def lens_config_path() -> Path:
    return expand_path("~/.lens/config.json")


def system_temp_dir() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def session_writes_path(session: str) -> Path:
    """Cursor afterFileEdit side-channel for watched-write detection."""
    return expand_path("~/.lens/sessions") / session / "writes.txt"


def run_log_path(vault_root: Path) -> Path:
    return vault_root / "Metadata" / "usage" / "lens_runs.jsonl"


INVOCATION_TEMPLATE = (
    "Invoke the `lens` agent with: "
    "lens=<stem from config default_lens or explicit>, "
    "area=<from config default_area or explicit>, round=<n>, "
    'deliverable="<stable key>", files=[...], sources=[...], '
    "and on rounds after the first: prior_findings + your reaction per finding. "
    "Reuse the same deliverable key every round."
)
