"""Config: LENS_PATH / LENS_LOG_PATH → ~/.lens/config.json → error."""

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
    lens_path: Path
    log_path: Path
    enforce: bool = True
    watch_globs: List[str] = field(default_factory=lambda: list(DEFAULT_WATCH_GLOBS))
    source: str = "unknown"  # "env" | "config" | "env+config"


class ConfigError(Exception):
    pass


SETUP_INSTRUCTIONS = """\
Lens config missing. Create ~/.lens/config.json:

{
  "lens_path": "/absolute/path/to/your-lens.md",
  "log_path": "/absolute/path/to/lens_runs.jsonl",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}

Or set LENS_PATH and LENS_LOG_PATH to absolute file paths.
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


def _require_path(value: Any, label: str) -> Path:
    if not value or not isinstance(value, str):
        raise ConfigError(f"{label} missing or not a string\n\n{SETUP_INSTRUCTIONS}")
    return expand_path(value)


def resolve_config() -> Config:
    """Resolve lens_path + log_path. Raises ConfigError with setup text."""
    env_lens = os.environ.get("LENS_PATH", "").strip()
    env_log = os.environ.get("LENS_LOG_PATH", "").strip()
    file_data, file_path = _load_file()

    if env_lens or env_log:
        if not (env_lens and env_log):
            raise ConfigError(
                "LENS_PATH and LENS_LOG_PATH must both be set when using env overrides"
            )
        enforce = True
        watch = list(DEFAULT_WATCH_GLOBS)
        source = "env"
        if file_data:
            enforce = bool(file_data.get("enforce", True))
            watch = list(file_data.get("watch_globs") or DEFAULT_WATCH_GLOBS)
            source = "env+config"
        return Config(
            lens_path=_require_path(env_lens, "LENS_PATH"),
            log_path=_require_path(env_log, "LENS_LOG_PATH"),
            enforce=enforce,
            watch_globs=watch,
            source=source,
        )

    if file_data:
        return Config(
            lens_path=_require_path(file_data.get("lens_path"), "lens_path"),
            log_path=_require_path(file_data.get("log_path"), "log_path"),
            enforce=bool(file_data.get("enforce", True)),
            watch_globs=list(file_data.get("watch_globs") or DEFAULT_WATCH_GLOBS),
            source="config",
        )

    raise ConfigError(
        f"no config at {file_path}\n\n{SETUP_INSTRUCTIONS}"
        if file_path
        else SETUP_INSTRUCTIONS
    )


def write_config(
    lens_path: str,
    log_path: str,
    enforce: bool = True,
    watch_globs: Optional[List[str]] = None,
) -> Path:
    path = lens_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "lens_path": str(expand_path(lens_path)),
        "log_path": str(expand_path(log_path)),
        "enforce": enforce,
        "watch_globs": watch_globs or list(DEFAULT_WATCH_GLOBS),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
