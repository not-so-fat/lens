""" /lens-doctor — validate config, lens file, log, hooks, sandbox."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import ConfigError, resolve_config, write_config
from .lens_parse import parse_lens_file
from .log import ensure_log
from .sandbox import ensure_readonly_path, path_in_sandbox, sandbox_path
from .util import claude_home, cursor_home, expand_path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    checks: List[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name, ok, detail))


def _plugin_root() -> Optional[Path]:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("CURSOR_PLUGIN_ROOT")
    if env:
        return expand_path(env)
    here = Path(__file__).resolve()
    candidate = here.parents[2]
    if (candidate / ".claude-plugin").is_dir() or (candidate / ".cursor-plugin").is_dir():
        return candidate
    return None


def _hooks_registered_claude(plugin_root: Optional[Path]) -> tuple[bool, str]:
    if plugin_root:
        hooks = plugin_root / "hooks" / "claude-hooks.json"
        if hooks.is_file():
            try:
                data = json.loads(hooks.read_text(encoding="utf-8"))
                stop = (data.get("hooks") or {}).get("Stop")
                if stop:
                    return True, f"plugin hooks present: {hooks}"
            except json.JSONDecodeError as e:
                return False, f"invalid claude-hooks.json: {e}"
        return False, f"missing {hooks}"
    marketplaces = claude_home() / "plugins" / "marketplaces"
    if marketplaces.is_dir():
        for p in marketplaces.rglob("claude-hooks.json"):
            return True, f"found {p}"
    return False, "Claude hooks not found (install lens plugin)"


def _hooks_registered_cursor(plugin_root: Optional[Path]) -> tuple[bool, str]:
    if plugin_root:
        hooks = plugin_root / "hooks" / "cursor-hooks.json"
        if hooks.is_file():
            try:
                data = json.loads(hooks.read_text(encoding="utf-8"))
                root = data.get("hooks") if isinstance(data.get("hooks"), dict) else data
                if root.get("stop"):
                    return True, f"plugin hooks present: {hooks}"
            except json.JSONDecodeError as e:
                return False, f"invalid cursor-hooks.json: {e}"
        return False, f"missing {hooks}"
    user_hooks = cursor_home() / "hooks.json"
    if user_hooks.is_file():
        try:
            data = json.loads(user_hooks.read_text(encoding="utf-8"))
            hooks = data.get("hooks") or data
            if hooks.get("stop"):
                return True, f"user hooks.json has stop: {user_hooks}"
        except json.JSONDecodeError:
            pass
    return False, "Cursor stop hook not found (import lens plugin / Team Marketplace)"


def run_doctor(
    *,
    fix_sandbox: bool = True,
    write_lens: Optional[str] = None,
    write_log: Optional[str] = None,
) -> DoctorReport:
    report = DoctorReport()
    if write_lens or write_log:
        if not (write_lens and write_log):
            report.add(
                "write_config",
                False,
                "--write-lens and --write-log must be passed together",
            )
            return report
        path = write_config(write_lens, write_log)
        report.add("write_config", True, f"wrote {path}")

    try:
        cfg = resolve_config()
        report.add(
            "config",
            True,
            f"source={cfg.source} lens_path={cfg.lens_path} "
            f"log_path={cfg.log_path} enforce={cfg.enforce}",
        )
    except ConfigError as e:
        report.add("config", False, str(e))
        return report

    lens_ok = cfg.lens_path.is_file()
    report.add(
        "lens_file",
        lens_ok,
        str(cfg.lens_path) if lens_ok else f"not a file: {cfg.lens_path}",
    )
    if lens_ok:
        parsed = parse_lens_file(cfg.lens_path)
        report.add(
            "lens_shape",
            parsed.ok,
            (
                f"ok; check_blocks={parsed.check_blocks}"
                if parsed.ok
                else "; ".join(parsed.errors)
            ),
        )
    else:
        report.add("lens_shape", False, "skipped — lens file missing")

    try:
        log_path = ensure_log(cfg.log_path)
        writable = os.access(log_path.parent, os.W_OK)
        report.add("log_writable", writable, str(cfg.log_path))
    except OSError as e:
        report.add("log_writable", False, str(e))

    plugin_root = _plugin_root()
    ok_c, detail_c = _hooks_registered_claude(plugin_root)
    report.add("claude_hooks", ok_c, detail_c)
    ok_u, detail_u = _hooks_registered_cursor(plugin_root)
    report.add("cursor_hooks", ok_u, detail_u)

    readonly_target = cfg.lens_path.parent
    if fix_sandbox:
        try:
            spath, changed = ensure_readonly_path(readonly_target)
            report.add(
                "cursor_sandbox",
                True,
                f"{spath} additionalReadonlyPaths includes {readonly_target}"
                + (" (updated)" if changed else ""),
            )
        except OSError as e:
            report.add("cursor_sandbox", False, str(e))
    else:
        ok = path_in_sandbox(readonly_target)
        report.add(
            "cursor_sandbox",
            ok,
            (
                f"{sandbox_path()} includes {readonly_target}"
                if ok
                else f"{readonly_target} not in {sandbox_path()} additionalReadonlyPaths"
            ),
        )

    return report


def print_report(report: DoctorReport, file=None) -> int:
    file = file or sys.stdout
    for c in report.checks:
        mark = "PASS" if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}", file=file)
    if report.ok:
        print("lens-doctor: all checks green", file=file)
        return 0
    print("lens-doctor: FAILED", file=file)
    return 1
