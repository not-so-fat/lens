"""Codex install + validation for /lens-doctor (F6).

Codex is installed as a doctor-managed user install rather than a marketplace
plugin: we render the repo templates into ~/.codex/ with **absolute** script
paths (so nothing depends on an env var Codex may or may not set), and validate
that the log directory is writable from Codex's sandbox.

Writes only our own files (~/.codex/agents/lens.toml, ~/.codex/hooks.json,
merged non-destructively). Never mutates ~/.codex/config.toml — the user's
sandbox config is theirs; we validate and print the exact snippet to add.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .util import codex_home

try:  # tomllib is stdlib on 3.11+; validation degrades gracefully without it.
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore

CODEX_SCRIPTS = {
    "UserPromptSubmit": "python/codex_user_prompt.py",
    "PostToolUse": "python/codex_post_tool_use.py",
    "Stop": "python/codex_stop.py",
}


def codex_agents_dir() -> Path:
    return codex_home() / "agents"


def codex_agent_path() -> Path:
    return codex_agents_dir() / "lens.toml"


def codex_hooks_path() -> Path:
    return codex_home() / "hooks.json"


def codex_config_toml_path() -> Path:
    return codex_home() / "config.toml"


def _substitute(text: str, plugin_root: Path) -> str:
    root = str(plugin_root)
    return text.replace("${CODEX_PLUGIN_ROOT}", root).replace("$CODEX_PLUGIN_ROOT", root)


def _is_lens_command(cmd: str) -> bool:
    return any(Path(s).name in cmd for s in CODEX_SCRIPTS.values())


def install_agent(plugin_root: Path) -> Tuple[Path, bool]:
    """Render agents/codex/lens.toml → ~/.codex/agents/lens.toml (absolute paths)."""
    template = plugin_root / "agents" / "codex" / "lens.toml"
    rendered = _substitute(template.read_text(encoding="utf-8"), plugin_root)
    dest = codex_agent_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    old = dest.read_text(encoding="utf-8") if dest.is_file() else None
    if old == rendered:
        return dest, False
    dest.write_text(rendered, encoding="utf-8")
    return dest, True


def install_hooks(plugin_root: Path) -> Tuple[Path, bool]:
    """Merge lens hook commands into ~/.codex/hooks.json (absolute, non-destructive)."""
    template = plugin_root / "hooks" / "codex-hooks.json"
    ours = json.loads(_substitute(template.read_text(encoding="utf-8"), plugin_root))
    our_hooks = ours.get("hooks", {})

    dest = codex_hooks_path()
    existing = {}
    if dest.is_file():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    merged = dict(existing)
    hooks = dict(merged.get("hooks", {}))
    for event, groups in our_hooks.items():
        # Drop any prior lens entries for this event, keep the user's others.
        kept = []
        for grp in hooks.get(event, []):
            inner = [h for h in grp.get("hooks", []) if not _is_lens_command(h.get("command", ""))]
            if inner:
                kept.append({**grp, "hooks": inner})
        merged_groups = kept + list(groups)
        hooks[event] = merged_groups
    merged["hooks"] = hooks
    merged.setdefault("description", ours.get("description", "Lens enforcement for Codex"))

    new_text = json.dumps(merged, indent=2) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    old = dest.read_text(encoding="utf-8") if dest.is_file() else None
    if old == new_text:
        return dest, False
    dest.write_text(new_text, encoding="utf-8")
    return dest, True


def _writable_roots_from_config() -> Tuple[Optional[str], List[str]]:
    """Return (sandbox_mode, writable_roots) from ~/.codex/config.toml, best-effort."""
    path = codex_config_toml_path()
    if not path.is_file() or tomllib is None:
        return None, []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, []
    mode = data.get("sandbox_mode")
    ws = data.get("sandbox_workspace_write") or {}
    roots = ws.get("writable_roots") or []
    roots = [str(r) for r in roots if isinstance(r, str)]
    return (mode if isinstance(mode, str) else None), roots


def writable_roots_status(cfg: Config) -> Tuple[bool, str]:
    """Validate the worker can append the run log from Codex's sandbox.

    The read-only reviewer never writes the log — the worker does — so in
    workspace-write mode the log dir (outside the workspace) must be in
    writable_roots. read-only/untrusted mode or an absent config gets a note,
    not a failure (writes there prompt for approval rather than silently fail).
    """
    log_dir = str(Path(os.path.expanduser(str(cfg.log_path))).resolve().parent)
    mode, roots = _writable_roots_from_config()
    covered = any(
        log_dir == str(Path(os.path.expanduser(r)).resolve())
        or log_dir.startswith(str(Path(os.path.expanduser(r)).resolve()) + os.sep)
        for r in roots
    )
    if tomllib is None:
        return True, "config.toml not parsed (tomllib unavailable) — ensure writable_roots covers " + log_dir
    if mode == "workspace-write" and not covered:
        return False, (
            f"log dir {log_dir} not in writable_roots (sandbox_mode=workspace-write). "
            f"Add to ~/.codex/config.toml:\n"
            f"[sandbox_workspace_write]\nwritable_roots = [\"{log_dir}\"]"
        )
    if covered:
        return True, f"writable_roots covers {log_dir}"
    return True, (
        f"sandbox_mode={mode or 'default'}: log appends to {log_dir} may prompt for "
        f"approval; add it to [sandbox_workspace_write].writable_roots to avoid prompts"
    )


def ensure_codex_install(plugin_root: Optional[Path]) -> Tuple[bool, str]:
    """Write agent + hooks into ~/.codex/. Returns (ok, detail)."""
    if plugin_root is None:
        return False, "plugin root not resolved — cannot render ~/.codex/ files"
    if not (plugin_root / "agents" / "codex" / "lens.toml").is_file():
        return False, f"missing template: {plugin_root}/agents/codex/lens.toml"
    try:
        agent_path, a_changed = install_agent(plugin_root)
        hooks_path, h_changed = install_hooks(plugin_root)
    except OSError as e:
        return False, f"install failed: {e}"
    tail = " (updated)" if (a_changed or h_changed) else ""
    return True, f"{agent_path}, {hooks_path}{tail}"


def codex_install_status(plugin_root: Optional[Path]) -> Tuple[bool, str]:
    """Validate ~/.codex/ install without writing."""
    agent = codex_agent_path()
    hooks = codex_hooks_path()
    missing = [str(p) for p in (agent, hooks) if not p.is_file()]
    if missing:
        return False, "not installed: " + ", ".join(missing) + " (run /lens-doctor)"
    try:
        data = json.loads(hooks.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"invalid {hooks}: {e}"
    cmds = json.dumps(data)
    for event, rel in CODEX_SCRIPTS.items():
        if Path(rel).name not in cmds:
            return False, f"{hooks}: no command wired for {rel} ({event})"
        # absolute-path expectation: the rendered command must point at a real file
    return True, f"{agent}, {hooks}"
