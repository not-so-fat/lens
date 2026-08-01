"""Config: named lenses + log_path in ~/.lens/config.json."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .util import expand_path, lens_config_path

DEFAULT_WATCH_GLOBS = ["**/*.md", "**/*.html", "**/*.pptx"]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class Config:
    lenses: Dict[str, Path]
    log_path: Path
    default_lens: str
    lenses_dir: Optional[Path] = None
    enforce: bool = True
    watch_globs: List[str] = field(default_factory=lambda: list(DEFAULT_WATCH_GLOBS))
    source: str = "config"


class ConfigError(Exception):
    pass


SETUP_INSTRUCTIONS = """\
Lens config missing. Create ~/.lens/config.json:

{
  "lenses": {
    "review": "/absolute/path/to/review.md",
    "deck": "/absolute/path/to/deck.md"
  },
  "default_lens": "review",
  "log_path": "/absolute/path/to/lens_runs.jsonl",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}

Optional: "lenses_dir": "/absolute/path/to/dir" — names not listed in
`lenses` resolve to <lenses_dir>/<name>.md (drop a file to add a lens).

Or: PYTHONPATH=python python3 -m lens_lib lens add <name> <path>
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


def _parse_lenses(raw: Any) -> Dict[str, Path]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("`lenses` must be an object of name → absolute path")
    out: Dict[str, Path] = {}
    for name, path in raw.items():
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise ConfigError(
                f"invalid lens name {name!r} — use kebab-case [a-z0-9-]+"
            )
        if not isinstance(path, str):
            raise ConfigError(f"lenses.{name} must be a string path")
        out[name] = expand_path(path)
    return out


def _from_data(data: dict, source: str) -> Config:
    log_path = _require_path(data.get("log_path"), "log_path")
    lenses = _parse_lenses(data.get("lenses"))
    lenses_dir_raw = data.get("lenses_dir")
    lenses_dir = expand_path(lenses_dir_raw) if lenses_dir_raw else None

    default_lens = data.get("default_lens")
    if not default_lens or not isinstance(default_lens, str):
        if len(lenses) == 1:
            default_lens = next(iter(lenses))
        else:
            raise ConfigError(
                "default_lens is required when multiple (or zero named) lenses "
                f"are configured\n\n{SETUP_INSTRUCTIONS}"
            )
    if not NAME_RE.match(default_lens):
        raise ConfigError(f"invalid default_lens {default_lens!r}")

    cfg = Config(
        lenses=lenses,
        log_path=log_path,
        default_lens=default_lens,
        lenses_dir=lenses_dir,
        enforce=bool(data.get("enforce", True)),
        watch_globs=(
            list(data["watch_globs"] or [])
            if "watch_globs" in data
            else list(DEFAULT_WATCH_GLOBS)
        ),
        source=source,
    )
    # Ensure default resolves
    resolve_lens(cfg, None)
    return cfg


def resolve_config() -> Config:
    """Load config. Env LENS_LOG_PATH overrides log_path; LENS_DEFAULT overrides default_lens."""
    file_data, file_path = _load_file()
    if not file_data:
        raise ConfigError(
            f"no config at {file_path}\n\n{SETUP_INSTRUCTIONS}"
            if file_path
            else SETUP_INSTRUCTIONS
        )

    source = "config"
    data = dict(file_data)
    env_log = os.environ.get("LENS_LOG_PATH", "").strip()
    env_default = os.environ.get("LENS_DEFAULT", "").strip()
    if env_log:
        data["log_path"] = env_log
        source = "env+config"
    if env_default:
        data["default_lens"] = env_default
        source = "env+config"
    return _from_data(data, source)


def resolve_lens(cfg: Config, name: Optional[str] = None) -> Tuple[str, Path]:
    """
    Resolve a lens name to (name, absolute path).
    name=None → cfg.default_lens.
    Order: explicit `lenses` map, then `lenses_dir/<name>.md`.
    """
    key = name or cfg.default_lens
    if not key or not isinstance(key, str):
        raise ConfigError("lens name missing")
    if not NAME_RE.match(key):
        raise ConfigError(f"invalid lens name {key!r} — use kebab-case [a-z0-9-]+")

    if key in cfg.lenses:
        path = cfg.lenses[key]
        return key, path

    if cfg.lenses_dir is not None:
        candidate = cfg.lenses_dir / f"{key}.md"
        if candidate.is_file():
            return key, candidate.resolve()

    known = sorted(set(cfg.lenses) | set(list_dir_lens_names(cfg)))
    hint = f" Known: {', '.join(known)}" if known else ""
    raise ConfigError(f"unknown lens {key!r}.{hint}\n\n{SETUP_INSTRUCTIONS}")


def list_dir_lens_names(cfg: Config) -> List[str]:
    if cfg.lenses_dir is None or not cfg.lenses_dir.is_dir():
        return []
    return sorted(
        p.stem
        for p in cfg.lenses_dir.glob("*.md")
        if p.is_file() and NAME_RE.match(p.stem)
    )


def list_lens_names(cfg: Config) -> List[str]:
    return sorted(set(cfg.lenses) | set(list_dir_lens_names(cfg)))


def readonly_roots(cfg: Config) -> List[Path]:
    """Directories Cursor sandbox should allow reading."""
    roots: List[Path] = []
    for path in cfg.lenses.values():
        roots.append(path.parent)
    if cfg.lenses_dir is not None:
        roots.append(cfg.lenses_dir)
    # unique preserve order
    seen = set()
    out: List[Path] = []
    for r in roots:
        key = str(r.resolve())
        if key not in seen:
            seen.add(key)
            out.append(r.resolve())
    return out


def load_raw() -> dict:
    data, path = _load_file()
    if not data:
        raise ConfigError(
            f"no config at {path}\n\n{SETUP_INSTRUCTIONS}"
            if path
            else SETUP_INSTRUCTIONS
        )
    return data


def save_raw(data: dict) -> Path:
    path = lens_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_config(
    log_path: str,
    lenses: Optional[Dict[str, str]] = None,
    default_lens: Optional[str] = None,
    lenses_dir: Optional[str] = None,
    enforce: bool = True,
    watch_globs: Optional[List[str]] = None,
) -> Path:
    payload: dict[str, Any] = {
        "log_path": str(expand_path(log_path)),
        "enforce": enforce,
        "watch_globs": (
            list(DEFAULT_WATCH_GLOBS) if watch_globs is None else list(watch_globs)
        ),
    }
    mapped = {k: str(expand_path(v)) for k, v in (lenses or {}).items()}
    if mapped:
        payload["lenses"] = mapped
    if default_lens:
        payload["default_lens"] = default_lens
    elif len(mapped) == 1:
        payload["default_lens"] = next(iter(mapped))
    if lenses_dir:
        payload["lenses_dir"] = str(expand_path(lenses_dir))
    # validate before write
    _from_data(payload, "config")
    return save_raw(payload)


def add_lens(name: str, path: str, *, make_default: bool = False) -> Path:
    if not NAME_RE.match(name):
        raise ConfigError(f"invalid lens name {name!r}")
    data, cfg_path = _load_file()
    if not data:
        raise ConfigError(
            f"no config at {cfg_path} — create one first (see setup instructions)"
        )
    lenses = dict(data.get("lenses") or {})
    lenses[name] = str(expand_path(path))
    data["lenses"] = lenses
    if make_default or not data.get("default_lens"):
        data["default_lens"] = name
    _from_data(data, "config")
    return save_raw(data)


def remove_lens(name: str) -> Path:
    data, cfg_path = _load_file()
    if not data:
        raise ConfigError(f"no config at {cfg_path}")
    lenses = dict(data.get("lenses") or {})
    if name not in lenses:
        raise ConfigError(f"lens {name!r} not in config lenses map")
    del lenses[name]
    data["lenses"] = lenses
    if data.get("default_lens") == name:
        if lenses:
            data["default_lens"] = sorted(lenses)[0]
        else:
            data.pop("default_lens", None)
    return save_raw(data)
