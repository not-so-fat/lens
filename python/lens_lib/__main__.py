"""CLI: python -m lens_lib <doctor|close|append-run|record-write>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Allow `python path/to/python -m lens_lib` when parent is on sys.path
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import print_report, run_doctor

    report = run_doctor(
        lens_name=args.lens,
        fix_sandbox=not args.no_fix_sandbox,
        write_vault=args.write_config,
    )
    return print_report(report)


def cmd_close(args: argparse.Namespace) -> int:
    from .close import close_deliverable

    try:
        record, path = close_deliverable(
            args.deliverable,
            args.corrections,
            misses=args.miss or None,
            noise=args.noise or None,
        )
    except (ValueError, Exception) as e:
        print(f"lens-close: {e}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False))
    print(f"appended to {path}", file=sys.stderr)
    return 0


def cmd_append_run(args: argparse.Namespace) -> int:
    from .config import resolve_config
    from .log import append_record, validate_lens_run_shape

    raw = args.json or sys.stdin.read()
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"append-run: invalid JSON: {e}", file=sys.stderr)
        return 1
    record["event"] = "lens_run"
    if args.host:
        record["host"] = args.host
    errors = validate_lens_run_shape(record)
    if errors:
        print("append-run: " + "; ".join(errors), file=sys.stderr)
        return 1
    cfg = resolve_config()
    path = append_record(cfg.vault_root, record)
    print(path)
    return 0


def cmd_record_write(args: argparse.Namespace) -> int:
    from .check import record_sidechannel_write

    record_sidechannel_write(args.session, args.file_path)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="lens_lib")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_doc = sub.add_parser("doctor", help="validate lens install")
    p_doc.add_argument(
        "--lens",
        default=None,
        help="lens file stem (default: config default_lens, else first under Direction/Lenses/)",
    )
    p_doc.add_argument("--write-config", metavar="VAULT_ROOT")
    p_doc.add_argument("--no-fix-sandbox", action="store_true")
    p_doc.set_defaults(func=cmd_doctor)

    p_close = sub.add_parser("close", help="append human_review")
    p_close.add_argument("deliverable")
    p_close.add_argument("--corrections", type=int, required=True)
    p_close.add_argument("--miss", action="append", default=[])
    p_close.add_argument("--noise", action="append", default=[])
    p_close.set_defaults(func=cmd_close)

    p_app = sub.add_parser("append-run", help="append lens_run JSON")
    p_app.add_argument("--json", help="lens_run JSON object")
    p_app.add_argument("--host", choices=["claude-code", "cursor"])
    p_app.set_defaults(func=cmd_append_run)

    p_rw = sub.add_parser("record-write", help="Cursor afterFileEdit side-channel")
    p_rw.add_argument("--session", required=True)
    p_rw.add_argument("--file-path", required=True)
    p_rw.set_defaults(func=cmd_record_write)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
