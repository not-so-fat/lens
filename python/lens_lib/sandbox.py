"""Merge vault_root into ~/.cursor/sandbox.json additionalReadonlyPaths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .util import cursor_home, expand_path


def sandbox_path() -> Path:
    return cursor_home() / "sandbox.json"


def ensure_vault_readonly(vault_root: Path) -> Tuple[Path, bool]:
    """
    Ensure vault_root is listed under additionalReadonlyPaths.
    Returns (path, changed).
    """
    path = sandbox_path()
    vault = str(expand_path(str(vault_root)))
    data: Dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}

    key = "additionalReadonlyPaths"
    existing: List[str] = list(data.get(key) or [])
    normalized = [str(expand_path(p)) for p in existing]
    if vault in normalized:
        return path, False

    existing.append(vault)
    data[key] = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path, True


def vault_in_sandbox(vault_root: Path) -> bool:
    path = sandbox_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    vault = str(expand_path(str(vault_root)))
    for p in data.get("additionalReadonlyPaths") or []:
        if str(expand_path(str(p))) == vault:
            return True
    return False
