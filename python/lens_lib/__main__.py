"""CLI: python -m lens_lib <doctor|close|skip|append-run|record-write|lens|corrections>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import print_report, run_doctor

    report = run_doctor(
        fix_sandbox=not args.no_fix_sandbox,
        write_log=args.write_log,
        write_lens_name=args.write_lens_name,
        write_lens_path=args.write_lens_path,
    )
    return print_report(report)


def cmd_close(args: argparse.Namespace) -> int:
    from .close import close_deliverable

    try:
        record, path, signals = close_deliverable(
            args.deliverable,
            args.corrections,
            run_id=args.run_id,
            lens=args.lens,
            session=args.session,
            misses=args.miss or None,
            noise=args.noise or None,
        )
    except Exception as e:
        print(f"lens-close: {e}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False))
    print(f"appended to {path}", file=sys.stderr)
    if signals:
        ids = ", ".join(s["id"] for s in signals)
        print(f"correction signals: {ids}", file=sys.stderr)
    return 0


def cmd_runs_list(args: argparse.Namespace) -> int:
    from .config import resolve_config
    from .log import format_run_candidate, list_lens_runs_for_deliverable

    cfg = resolve_config()
    runs = list_lens_runs_for_deliverable(cfg.log_path, args.deliverable)
    if not runs:
        print(f"no lens_run for deliverable {args.deliverable!r}", file=sys.stderr)
        return 1
    for rec in runs:
        print(format_run_candidate(rec))
    return 0


def cmd_skip(args: argparse.Namespace) -> int:
    from .skip import skip_deliverable

    try:
        record, path, appended = skip_deliverable(
            args.deliverable,
            session=args.session,
            reason=args.reason,
            host=args.host,
            workspace_root=getattr(args, "workspace_root", None),
        )
    except Exception as e:
        print(f"lens-skip: {e}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False))
    if appended:
        print(f"appended to {path}", file=sys.stderr)
    else:
        print(
            "lens-skip: pending batch already satisfied; skipped append",
            file=sys.stderr,
        )
    return 0


def cmd_append_run(args: argparse.Namespace) -> int:
    from .config import resolve_config
    from .log import append_record, is_duplicate_lens_run, new_run_id, validate_lens_run_shape

    raw = args.json or sys.stdin.read()
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"append-run: invalid JSON: {e}", file=sys.stderr)
        return 1
    record["event"] = "lens_run"
    if not record.get("run_id"):
        record["run_id"] = new_run_id()
    if args.host:
        record["host"] = args.host
    if getattr(args, "session", None):
        record["session"] = args.session
    errors = validate_lens_run_shape(record)
    if errors:
        print("append-run: " + "; ".join(errors), file=sys.stderr)
        return 1
    cfg = resolve_config()
    if is_duplicate_lens_run(cfg.log_path, record):
        print(str(cfg.log_path))
        print(
            "append-run: identical terminal lens_run already logged; skipped",
            file=sys.stderr,
        )
        if record.get("run_id"):
            print(f"lens_run_id: {record['run_id']}", file=sys.stderr)
        return 0
    path = append_record(cfg.log_path, record)
    print(path)
    print(f"lens_run_id: {record['run_id']}", file=sys.stderr)
    return 0


def cmd_record_write(args: argparse.Namespace) -> int:
    from .check import record_sidechannel_write

    record_sidechannel_write(
        args.session,
        args.file_path,
        workspace_root=getattr(args, "workspace_root", None),
    )
    return 0


def cmd_lens_list(_: argparse.Namespace) -> int:
    from .config import ConfigError, list_lens_names, resolve_config, resolve_lens

    try:
        cfg = resolve_config()
        for name in list_lens_names(cfg):
            _, path = resolve_lens(cfg, name)
            mark = "*" if name == cfg.default_lens else " "
            print(f"{mark} {name}\t{path}")
    except ConfigError as e:
        print(f"lens: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_lens_add(args: argparse.Namespace) -> int:
    from .config import ConfigError, add_lens

    try:
        path = add_lens(args.name, args.path, make_default=args.default)
        print(f"added {args.name} → {args.path} ({path})")
    except ConfigError as e:
        print(f"lens: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_lens_remove(args: argparse.Namespace) -> int:
    from .config import ConfigError, remove_lens

    try:
        path = remove_lens(args.name)
        print(f"removed {args.name} ({path})")
    except ConfigError as e:
        print(f"lens: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_corrections_list(args: argparse.Namespace) -> int:
    from .corrections import list_patches, list_signals

    status = None if args.status == "all" else args.status
    if args.kind in ("signals", "both"):
        sig_status = status
        if status == "proposed":
            sig_status = "open"
        signals = list_signals(lens=args.lens, status=sig_status)
        for rec in signals:
            print(json.dumps(rec, ensure_ascii=False))
    if args.kind in ("patches", "both"):
        pat_status = status
        if status == "open":
            pat_status = "proposed"
        patches = list_patches(lens=args.lens, status=pat_status)
        for rec in patches:
            print(json.dumps(rec, ensure_ascii=False))
    return 0


def cmd_corrections_show(args: argparse.Namespace) -> int:
    from .corrections import get_patch, get_signal, preview_patch

    item_id = args.id
    if item_id.startswith("cs_"):
        rec = get_signal(item_id)
        if not rec:
            print(f"corrections: unknown signal {item_id!r}", file=sys.stderr)
            return 1
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return 0
    if item_id.startswith("lp_"):
        rec = get_patch(item_id)
        if not rec:
            print(f"corrections: unknown patch {item_id!r}", file=sys.stderr)
            return 1
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        if args.diff:
            print(preview_patch(item_id), end="")
        return 0
    print(f"corrections: id must start with cs_ or lp_", file=sys.stderr)
    return 1


def cmd_corrections_propose(args: argparse.Namespace) -> int:
    from .corrections import preview_patch, propose_patch

    raw = Path(args.ops_file).read_text(encoding="utf-8")
    try:
        ops_payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"corrections propose: invalid JSON: {e}", file=sys.stderr)
        return 1
    ops = ops_payload if isinstance(ops_payload, list) else ops_payload.get("ops")
    if not isinstance(ops, list) or not ops:
        print("corrections propose: ops file must be a JSON array or {ops: [...]}", file=sys.stderr)
        return 1
    signal_ids = [s.strip() for s in args.signal_ids.split(",") if s.strip()]
    try:
        patch = propose_patch(
            lens=args.lens,
            signal_ids=signal_ids,
            ops=ops,
            force=args.force,
        )
    except Exception as e:
        print(f"corrections propose: {e}", file=sys.stderr)
        return 1
    print(json.dumps(patch, ensure_ascii=False, indent=2))
    if args.preview:
        print(preview_patch(patch["id"]), end="")
    return 0


def cmd_corrections_funnel(_: argparse.Namespace) -> int:
    from .corrections import funnel_stats

    print(json.dumps(funnel_stats(), ensure_ascii=False, indent=2))
    return 0


def cmd_corrections_apply(args: argparse.Namespace) -> int:
    from .corrections import apply_patch

    try:
        path, patch = apply_patch(args.patch_id)
    except Exception as e:
        print(f"corrections apply: {e}", file=sys.stderr)
        return 1
    print(f"applied {patch['id']} → {path}")
    print("run /lens-doctor to verify; consider committing your lens file.", file=sys.stderr)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="lens_lib")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_doc = sub.add_parser("doctor", help="validate lens install")
    p_doc.add_argument("--write-log", metavar="PATH")
    p_doc.add_argument("--write-lens-name", metavar="NAME")
    p_doc.add_argument("--write-lens-path", metavar="PATH")
    p_doc.add_argument("--no-fix-sandbox", action="store_true")
    p_doc.set_defaults(func=cmd_doctor)

    p_close = sub.add_parser("close", help="append human_review")
    p_close.add_argument(
        "deliverable",
        nargs="?",
        help="deliverable key (optional when --run-id is set)",
    )
    p_close.add_argument("--corrections", type=int, required=True)
    p_close.add_argument(
        "--run-id",
        help="terminal lens_run id from append stderr (lr_…); required when ambiguous",
    )
    p_close.add_argument("--lens", help="disambiguate deliverable-only close")
    p_close.add_argument("--session", help="disambiguate deliverable-only close")
    p_close.add_argument("--miss", action="append", default=[])
    p_close.add_argument("--noise", action="append", default=[])
    p_close.set_defaults(func=cmd_close)

    p_runs = sub.add_parser("runs", help="inspect lens_run rows")
    runs_sub = p_runs.add_subparsers(dest="runs_cmd", required=True)
    p_runs_list = runs_sub.add_parser("list", help="list runs for a deliverable")
    p_runs_list.add_argument("--deliverable", required=True)
    p_runs_list.set_defaults(func=cmd_runs_list)

    p_skip = sub.add_parser("skip", help="append lens_skip (owner deliberately held)")
    p_skip.add_argument("deliverable")
    p_skip.add_argument(
        "--session",
        help="conversation/session id to stamp so the Stop gate clears for it",
    )
    p_skip.add_argument("--reason", help="why the review was held")
    p_skip.add_argument("--host", choices=["claude-code", "cursor", "codex"])
    p_skip.add_argument(
        "--workspace-root",
        help="workspace root for (workspace, conversation) side-channel key",
    )
    p_skip.set_defaults(func=cmd_skip)

    p_app = sub.add_parser("append-run", help="append lens_run JSON")
    p_app.add_argument("--json", help="lens_run JSON object")
    p_app.add_argument("--host", choices=["claude-code", "cursor", "codex"])
    p_app.add_argument(
        "--session",
        help="conversation/session id to stamp on the lens_run (Cursor gate backup)",
    )
    p_app.set_defaults(func=cmd_append_run)

    p_rw = sub.add_parser("record-write", help="Cursor afterFileEdit side-channel")
    p_rw.add_argument("--session", required=True)
    p_rw.add_argument("--file-path", required=True)
    p_rw.add_argument(
        "--workspace-root",
        help="workspace root for (workspace, conversation) side-channel key",
    )
    p_rw.set_defaults(func=cmd_record_write)

    p_lens = sub.add_parser("lens", help="manage named lenses")
    lens_sub = p_lens.add_subparsers(dest="lens_cmd", required=True)
    p_list = lens_sub.add_parser("list", help="list configured lenses")
    p_list.set_defaults(func=cmd_lens_list)
    p_add = lens_sub.add_parser("add", help="register a named lens path")
    p_add.add_argument("name")
    p_add.add_argument("path")
    p_add.add_argument("--default", action="store_true")
    p_add.set_defaults(func=cmd_lens_add)
    p_rm = lens_sub.add_parser("remove", help="unregister a named lens")
    p_rm.add_argument("name")
    p_rm.set_defaults(func=cmd_lens_remove)

    p_corr = sub.add_parser("corrections", help="correction capture rail")
    corr_sub = p_corr.add_subparsers(dest="corr_cmd", required=True)

    p_cl = corr_sub.add_parser("list", help="list signals and/or patches")
    p_cl.add_argument("--lens", help="filter by lens name")
    p_cl.add_argument(
        "--status",
        default="open",
        choices=["open", "actioned", "discarded", "proposed", "accepted", "all"],
    )
    p_cl.add_argument(
        "--kind",
        default="both",
        choices=["signals", "patches", "both"],
    )
    p_cl.set_defaults(func=cmd_corrections_list)

    p_cs = corr_sub.add_parser("show", help="show one signal or patch")
    p_cs.add_argument("id", help="cs_… or lp_…")
    p_cs.add_argument("--diff", action="store_true", help="for lp_…, print markdown diff")
    p_cs.set_defaults(func=cmd_corrections_show)

    p_cp = corr_sub.add_parser("propose", help="propose lens patch from signals")
    p_cp.add_argument("--lens", required=True)
    p_cp.add_argument("--signal-ids", required=True, help="comma-separated cs_… ids")
    p_cp.add_argument("--ops-file", required=True, help="JSON file with ops array")
    p_cp.add_argument("--force", action="store_true", help="allow single signal")
    p_cp.add_argument("--preview", action="store_true", help="print diff after propose")
    p_cp.set_defaults(func=cmd_corrections_propose)

    p_ca = corr_sub.add_parser("apply", help="apply proposed patch to lens file")
    p_ca.add_argument("patch_id", help="lp_…")
    p_ca.set_defaults(func=cmd_corrections_apply)

    p_cf = corr_sub.add_parser("funnel", help="correction flywheel counts")
    p_cf.set_defaults(func=cmd_corrections_funnel)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
