"""Grant the Claude Code lens runner its out-of-workspace access.

The reviewer subagent must Read the lens files (which live outside the repo —
`~/.lens/config.json` and the lens markdown under the owner's vault) and the run
is appended via the plugin CLI. In an interactive session the user approves those
prompts; a **background** subagent cannot prompt, so the calls auto-deny and the
review can't run. This is the claude-code analog of the Cursor sandbox
(`sandbox.py`): it pre-grants the access in `~/.claude/settings.json` so no prompt
is needed. Shares `readonly_roots(cfg)` with the Cursor path — one source of truth
for "which dirs the runner reads".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import Config, readonly_roots
from .util import claude_home, expand_path


class ClaudePermsError(Exception):
    """settings.json exists but is unreadable/unparseable — refuse to overwrite.

    A present-but-corrupt file is user data we must not clobber: silently
    treating it as `{}` and rewriting would drop every other setting.
    """


def settings_path() -> Path:
    """Global Claude settings — mirrors the global ~/.cursor/sandbox.json."""
    return claude_home() / "settings.json"


def _read_entry(target: Path) -> str:
    """A Read() allow rule for a directory, tilde-relative under $HOME."""
    ap = str(expand_path(str(target)))
    home = str(expand_path("~"))
    if ap == home or ap.startswith(home + "/"):
        return f"Read(~{ap[len(home):]}/**)"
    return f"Read(//{ap.lstrip('/')}/**)"


def required_allow(cfg: Config) -> List[str]:
    """Permission allow-rules the runner needs, in a stable order."""
    entries: List[str] = [_read_entry(root) for root in readonly_roots(cfg)]
    # config + run log live under ~/.lens
    entries.append("Read(~/.lens/**)")
    # A terminal round appends the lens_run via the append launcher, invoked as a
    # bare `python3 <path>` (NO leading `PYTHONPATH=`): Claude Code allow-rules
    # don't match past an env-var assignment, so this is the pre-grantable form a
    # background subagent can run without a prompt. Matches agents/lens.md.
    #
    # The runner writes `${CLAUDE_PLUGIN_ROOT}` (agents/lens.md), which the shell
    # expands at exec. We can't observe whether the permission matcher compares
    # the command before or after expansion, so grant BOTH forms — the literal
    # `${CLAUDE_PLUGIN_ROOT}` (pre-expansion match) and the resolved absolute path
    # (post-expansion match, same approach as the Read roots above). Whichever the
    # matcher uses, one hits; the other is inert.
    launcher = Path(__file__).resolve().parent.parent / "lens_append.py"
    entries.append('Bash(python3 "${CLAUDE_PLUGIN_ROOT}/python/lens_append.py":*)')
    entries.append(f'Bash(python3 "{launcher}":*)')
    entries.append("Bash(date:*)")
    seen: set = set()
    out: List[str] = []
    for e in entries:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _load() -> Dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        # An empty file carries no settings to preserve — safe to (re)write.
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClaudePermsError(f"{path} is not valid JSON ({e}); refusing to overwrite")
    if not isinstance(data, dict):
        raise ClaudePermsError(f"{path} is not a JSON object; refusing to overwrite")
    return data


def _current_allow() -> List[str]:
    perms = _load().get("permissions")
    if isinstance(perms, dict) and isinstance(perms.get("allow"), list):
        return list(perms["allow"])
    return []


def missing_allow(cfg: Config) -> List[str]:
    have = set(_current_allow())
    return [e for e in required_allow(cfg) if e not in have]


def ensure_allow(cfg: Config) -> Tuple[Path, bool]:
    """Merge the required allow-rules into settings.json. Returns (path, changed)."""
    path = settings_path()
    data = _load()
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
    allow: List[str] = list(perms.get("allow") or [])
    have = set(allow)
    changed = False
    for e in required_allow(cfg):
        if e not in have:
            allow.append(e)
            have.add(e)
            changed = True
    if changed:
        perms["allow"] = allow
        data["permissions"] = perms
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path, changed
