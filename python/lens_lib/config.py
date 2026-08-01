"""Config resolution: LENS_VAULT_ROOT → ~/.lens/config.json → error."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .util import expand_path, lens_config_path

DEFAULT_WATCH_GLOBS = ["**/*.md", "**/*.html", "**/*.pptx"]


@dataclass
class Config:
    vault_root: Path
    enforce: bool = True
    watch_globs: List[str] = field(default_factory=lambda: list(DEFAULT_WATCH_GLOBS))
    default_lens: Optional[str] = None
    default_area: Optional[str] = None
    source: str = "unknown"  # "env" | "config" | "env+config"


class ConfigError(Exception):
    pass


SETUP_INSTRUCTIONS = """\
Lens config missing. Create ~/.lens/config.json:

{
  "vault_root": "/absolute/path/to/your/vault",
  "default_lens": "<lens-file-stem>",
  "default_area": "<area-tag>",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}

Or set LENS_VAULT_ROOT to an absolute vault path.
Then run /lens-doctor.
"""


def _load_file() -> Tuple[Optional[dict], Optional[Path]]:
    path = lens_config_path()
    if not path.is_file():
        return None, path
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"config must be a JSON object: {path}")
    return data, path


def _optional_str(data: Optional[dict], key: str) -> Optional[str]:
    if not data:
        return None
    val = data.get(key)
    if val is None or val == "":
        return None
    if not isinstance(val, str):
        raise ConfigError(f"{key} must be a string")
    return val


def resolve_config() -> Config:
    """Resolve vault_root and options. Raises ConfigError with setup text."""
    env_root = os.environ.get("LENS_VAULT_ROOT", "").strip()
    file_data, file_path = _load_file()

    if env_root:
        vault = expand_path(env_root)
        enforce = True
        watch = list(DEFAULT_WATCH_GLOBS)
        source = "env"
        default_lens = _optional_str(file_data, "default_lens")
        default_area = _optional_str(file_data, "default_area")
        if file_data:
            enforce = bool(file_data.get("enforce", True))
            watch = list(file_data.get("watch_globs") or DEFAULT_WATCH_GLOBS)
            source = "env+config"
        return Config(
            vault_root=vault,
            enforce=enforce,
            watch_globs=watch,
            default_lens=default_lens,
            default_area=default_area,
            source=source,
        )

    if file_data:
        root = file_data.get("vault_root")
        if not root or not isinstance(root, str):
            raise ConfigError(
                f"vault_root missing in {file_path}\n\n{SETUP_INSTRUCTIONS}"
            )
        return Config(
            vault_root=expand_path(root),
            enforce=bool(file_data.get("enforce", True)),
            watch_globs=list(file_data.get("watch_globs") or DEFAULT_WATCH_GLOBS),
            default_lens=_optional_str(file_data, "default_lens"),
            default_area=_optional_str(file_data, "default_area"),
            source="config",
        )

    raise ConfigError(SETUP_INSTRUCTIONS)


def write_config(
    vault_root: str,
    enforce: bool = True,
    watch_globs: Optional[List[str]] = None,
    default_lens: Optional[str] = None,
    default_area: Optional[str] = None,
) -> Path:
    path = lens_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "vault_root": str(expand_path(vault_root)),
        "enforce": enforce,
        "watch_globs": watch_globs or list(DEFAULT_WATCH_GLOBS),
    }
    if default_lens:
        payload["default_lens"] = default_lens
    if default_area:
        payload["default_area"] = default_area
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
