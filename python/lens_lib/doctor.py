""" /lens-doctor — validate config, named lenses, log, hooks, sandbox."""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import (
    ConfigError,
    list_lens_names,
    readonly_roots,
    resolve_config,
    resolve_lens,
    write_config,
)
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


def _iter_command_strings(obj) -> List[str]:
    found: List[str] = []
    if isinstance(obj, dict):
        cmd = obj.get("command")
        if isinstance(cmd, str):
            found.append(cmd)
        for v in obj.values():
            found.extend(_iter_command_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_iter_command_strings(item))
    return found


def _validate_hook_commands(
    *,
    host: str,
    hooks_file: Path,
    plugin_root: Path,
    required_var: str,
    required_scripts: List[str],
) -> tuple[bool, str]:
    """Fail if commands use relative ./ paths or don't expand to real scripts."""
    try:
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"invalid {hooks_file.name}: {e}"

    commands = _iter_command_strings(data)
    if not commands:
        return False, f"no command entries in {hooks_file}"

    root_s = str(plugin_root)
    problems: List[str] = []
    for cmd in commands:
        if "./" in cmd and required_var not in cmd:
            problems.append(f"relative path without {required_var}: {cmd}")
        if required_var not in cmd:
            problems.append(f"missing {required_var}: {cmd}")
        expanded = (
            cmd.replace("${" + required_var + "}", root_s)
            .replace("$" + required_var, root_s)
        )
        try:
            tokens = shlex.split(expanded)
        except ValueError:
            tokens = expanded.replace('"', "").split()
        for token in tokens:
            if token.endswith(".py"):
                p = Path(token)
                if not p.is_file():
                    problems.append(f"script missing after expand: {token}")

    joined = " ".join(commands)
    for rel in required_scripts:
        target = plugin_root / rel
        if not target.is_file():
            problems.append(f"expected script missing: {target}")
        if Path(rel).name not in joined:
            problems.append(f"no hook command wired for {Path(rel).name}")

    if problems:
        return False, f"{host}: " + "; ".join(problems)
    return True, f"{host}: {hooks_file} commands wire {required_var} scripts"


def _hooks_registered_claude(plugin_root: Optional[Path]) -> tuple[bool, str]:
    if plugin_root:
        hooks = plugin_root / "hooks" / "claude-hooks.json"
        if not hooks.is_file():
            return False, f"missing {hooks}"
        return _validate_hook_commands(
            host="claude",
            hooks_file=hooks,
            plugin_root=plugin_root,
            required_var="CLAUDE_PLUGIN_ROOT",
            required_scripts=[
                "python/claude_stop.py",
                "python/claude_user_prompt.py",
            ],
        )
    marketplaces = claude_home() / "plugins" / "marketplaces"
    if marketplaces.is_dir():
        for p in marketplaces.rglob("claude-hooks.json"):
            root = p.parents[1] if p.parent.name == "hooks" else p.parent
            return _validate_hook_commands(
                host="claude",
                hooks_file=p,
                plugin_root=root,
                required_var="CLAUDE_PLUGIN_ROOT",
                required_scripts=[
                    "python/claude_stop.py",
                    "python/claude_user_prompt.py",
                ],
            )
    return False, "Claude hooks not found (install lens plugin)"


def _hooks_registered_cursor(plugin_root: Optional[Path]) -> tuple[bool, str]:
    if plugin_root:
        hooks = plugin_root / "hooks" / "cursor-hooks.json"
        if not hooks.is_file():
            return False, f"missing {hooks}"
        return _validate_hook_commands(
            host="cursor",
            hooks_file=hooks,
            plugin_root=plugin_root,
            required_var="CURSOR_PLUGIN_ROOT",
            required_scripts=[
                "python/cursor_stop.py",
                "python/cursor_after_file_edit.py",
            ],
        )
    # Installed plugins under ~/.cursor/plugins (cache / local)
    plugins_root = cursor_home() / "plugins"
    if plugins_root.is_dir():
        for p in plugins_root.rglob("cursor-hooks.json"):
            if "lens" not in str(p).lower():
                continue
            root = p.parents[1] if p.parent.name == "hooks" else p.parent
            return _validate_hook_commands(
                host="cursor",
                hooks_file=p,
                plugin_root=root,
                required_var="CURSOR_PLUGIN_ROOT",
                required_scripts=[
                    "python/cursor_stop.py",
                    "python/cursor_after_file_edit.py",
                ],
            )
    user_hooks = cursor_home() / "hooks.json"
    if user_hooks.is_file():
        try:
            data = json.loads(user_hooks.read_text(encoding="utf-8"))
            hooks = data.get("hooks") or data
            if hooks.get("stop"):
                cmds = _iter_command_strings(hooks.get("stop"))
                if any("CURSOR_PLUGIN_ROOT" in c or "lens" in c for c in cmds):
                    return True, f"user hooks.json has lens stop: {user_hooks}"
                return (
                    False,
                    f"{user_hooks} has stop but no CURSOR_PLUGIN_ROOT/lens command — "
                    "import the lens plugin (do not rely on workspace-relative ./python)",
                )
        except json.JSONDecodeError:
            pass
    return False, "Cursor stop hook not found (import lens plugin / Team Marketplace)"


def run_doctor(
    *,
    fix_sandbox: bool = True,
    write_log: Optional[str] = None,
    write_lens_name: Optional[str] = None,
    write_lens_path: Optional[str] = None,
) -> DoctorReport:
    report = DoctorReport()
    if write_log or write_lens_name or write_lens_path:
        if not (write_log and write_lens_name and write_lens_path):
            report.add(
                "write_config",
                False,
                "pass --write-log, --write-lens-name, and --write-lens-path together",
            )
            return report
        try:
            path = write_config(
                write_log,
                lenses={write_lens_name: write_lens_path},
                default_lens=write_lens_name,
            )
            report.add("write_config", True, f"wrote {path}")
        except ConfigError as e:
            report.add("write_config", False, str(e))
            return report

    try:
        cfg = resolve_config()
        names = list_lens_names(cfg)
        report.add(
            "config",
            True,
            f"source={cfg.source} default_lens={cfg.default_lens!r} "
            f"lenses={names} log_path={cfg.log_path} enforce={cfg.enforce}",
        )
    except ConfigError as e:
        report.add("config", False, str(e))
        return report

    try:
        default_name, default_path = resolve_lens(cfg, None)
        report.add(
            "default_lens",
            default_path.is_file(),
            f"{default_name} → {default_path}",
        )
    except ConfigError as e:
        report.add("default_lens", False, str(e))
        return report

    # Validate shape for every configured/dir lens that exists
    shape_ok = True
    details: List[str] = []
    for name in list_lens_names(cfg):
        try:
            _, path = resolve_lens(cfg, name)
        except ConfigError as e:
            shape_ok = False
            details.append(f"{name}: {e}")
            continue
        if not path.is_file():
            shape_ok = False
            details.append(f"{name}: missing file {path}")
            continue
        parsed = parse_lens_file(path)
        if parsed.ok:
            details.append(f"{name}: ok (check_blocks={parsed.check_blocks})")
        else:
            shape_ok = False
            details.append(f"{name}: " + "; ".join(parsed.errors))
    report.add("lens_shape", shape_ok, "; ".join(details) if details else "no lenses")

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

    roots = readonly_roots(cfg)
    if not roots:
        roots = [default_path.parent]
    if fix_sandbox:
        try:
            changed_any = False
            spath = sandbox_path()
            for root in roots:
                spath, changed = ensure_readonly_path(root)
                changed_any = changed_any or changed
            report.add(
                "cursor_sandbox",
                True,
                f"{spath} includes {', '.join(str(r) for r in roots)}"
                + (" (updated)" if changed_any else ""),
            )
        except OSError as e:
            report.add("cursor_sandbox", False, str(e))
    else:
        missing = [r for r in roots if not path_in_sandbox(r)]
        report.add(
            "cursor_sandbox",
            not missing,
            (
                f"{sandbox_path()} includes all lens roots"
                if not missing
                else f"missing from sandbox: {', '.join(str(m) for m in missing)}"
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
