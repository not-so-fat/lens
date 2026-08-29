"""Correction capture: signals from /lens-close, propose/apply lens patches."""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .config import Config, resolve_config, resolve_lens
from .lens_parse import apply_lens_ops, parse_lens_file, render_patch_diff
from .log import ensure_log, iter_records
from .util import correction_signals_path, lens_patches_path, utc_now_iso

CHECK_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SIGNAL_ID_RE = re.compile(r"^cs_[a-z0-9]+$")
PATCH_ID_RE = re.compile(r"^lp_[a-z0-9]+$")


def _new_signal_id() -> str:
    return f"cs_{secrets.token_hex(6)}"


def _new_patch_id() -> str:
    return f"lp_{secrets.token_hex(6)}"


def _append_jsonl(path: Path, record: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def validate_correction_signal(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for k in ("ts", "event", "id", "lens", "deliverable", "check", "kind", "note", "status"):
        if k not in record:
            errors.append(f"missing {k}")
    if record.get("event") != "correction_signal":
        errors.append("event must be correction_signal")
    if record.get("id") and not SIGNAL_ID_RE.match(str(record["id"])):
        errors.append("bad id")
    for slug_field in ("lens", "check"):
        if record.get(slug_field) and not CHECK_SLUG_RE.match(str(record[slug_field])):
            errors.append(f"bad {slug_field} slug")
    if record.get("kind") not in ("miss", "noise"):
        errors.append("kind must be miss|noise")
    if record.get("status") not in ("open", "actioned", "discarded"):
        errors.append("status must be open|actioned|discarded")
    run_id = record.get("lens_run_id")
    if run_id is not None and not re.match(r"^lr_[a-f0-9]+$", str(run_id)):
        errors.append("bad lens_run_id")
    return errors


def validate_lens_patch(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for k in ("id", "status", "lens", "lens_path", "ops", "signal_ids", "created_at"):
        if k not in record:
            errors.append(f"missing {k}")
    if record.get("id") and not PATCH_ID_RE.match(str(record["id"])):
        errors.append("bad id")
    if record.get("status") not in ("proposed", "accepted", "rejected", "superseded"):
        errors.append("bad status")
    ops = record.get("ops")
    if not isinstance(ops, list) or not ops:
        errors.append("ops must be non-empty array")
    else:
        for i, op in enumerate(ops):
            if not isinstance(op, dict):
                errors.append(f"ops[{i}] not object")
                continue
            kind = op.get("op")
            if kind == "add_check":
                for k in ("block", "bullet"):
                    if k not in op:
                        errors.append(f"ops[{i}] add_check missing {k}")
                if op.get("check") and not CHECK_SLUG_RE.match(str(op["check"])):
                    errors.append(f"ops[{i}] bad check slug")
            elif kind == "amend_check":
                for k in ("check", "bullet"):
                    if k not in op:
                        errors.append(f"ops[{i}] amend_check missing {k}")
            elif kind == "add_guard":
                if "bullet" not in op:
                    errors.append(f"ops[{i}] add_guard missing bullet")
            else:
                errors.append(f"ops[{i}] unknown op {kind!r}")
    signal_ids = record.get("signal_ids")
    if not isinstance(signal_ids, list):
        errors.append("signal_ids must be array")
    else:
        for sid in signal_ids:
            if not SIGNAL_ID_RE.match(str(sid)):
                errors.append(f"bad signal id {sid!r}")
    return errors


def append_signal(record: Dict[str, Any]) -> Path:
    if "ts" not in record:
        record = {**record, "ts": utc_now_iso()}
    if "id" not in record:
        record = {**record, "id": _new_signal_id()}
    if record.get("linked_patch_id") is None and "linked_patch_id" not in record:
        record["linked_patch_id"] = None
    errors = validate_correction_signal(record)
    if errors:
        raise ValueError("; ".join(errors))
    return _append_jsonl(correction_signals_path(), record)


def append_patch(record: Dict[str, Any]) -> Path:
    if "created_at" not in record:
        record = {**record, "created_at": utc_now_iso()}
    if "id" not in record:
        record = {**record, "id": _new_patch_id()}
    errors = validate_lens_patch(record)
    if errors:
        raise ValueError("; ".join(errors))
    return _append_jsonl(lens_patches_path(), record)


def capture_from_human_review(
    *,
    run: Dict[str, Any],
    misses: Optional[List[dict]] = None,
    noise: Optional[List[dict]] = None,
) -> List[dict]:
    """Append correction_signal rows for misses/noise after /lens-close."""
    deliverable = str(run["deliverable"])
    lens_name = str(run["lens"])
    lens_run_id = run.get("run_id")
    lens_run_ts = str(run.get("ts") or "")
    signals: List[dict] = []
    for kind, items in (("miss", misses or []), ("noise", noise or [])):
        for item in items:
            sig = {
                "ts": utc_now_iso(),
                "event": "correction_signal",
                "id": _new_signal_id(),
                "lens": lens_name,
                "deliverable": deliverable,
                "check": item["check"],
                "kind": kind,
                "note": item["note"],
                "lens_run_ts": lens_run_ts,
                "status": "open",
                "linked_patch_id": None,
            }
            if lens_run_id:
                sig["lens_run_id"] = lens_run_id
            append_signal(sig)
            signals.append(sig)
    return signals


def funnel_stats(*, log_path: Optional[Path] = None) -> Dict[str, Any]:
    """Report correction-flywheel counts from append-only logs."""
    cfg = resolve_config()
    log = log_path or cfg.log_path
    terminal_runs = 0
    runs_with_id = 0
    human_reviews = 0
    reviews_with_run_id = 0
    for rec in iter_records(log):
        event = rec.get("event")
        if event == "lens_run":
            terminal_runs += 1
            if rec.get("run_id"):
                runs_with_id += 1
        elif event == "human_review":
            human_reviews += 1
            if rec.get("lens_run_id"):
                reviews_with_run_id += 1
    sig_path = correction_signals_path()
    patch_path = lens_patches_path()
    signals_open = len(list_signals(status="open"))
    signals_actioned = len(list_signals(status="actioned"))
    patches_proposed = len(list_patches(status="proposed"))
    patches_accepted = len(list_patches(status="accepted"))
    return {
        "log_path": str(log),
        "terminal_lens_runs": terminal_runs,
        "terminal_runs_with_run_id": runs_with_id,
        "human_reviews": human_reviews,
        "human_reviews_with_run_id": reviews_with_run_id,
        "correction_signals_open": signals_open,
        "correction_signals_actioned": signals_actioned,
        "lens_patches_proposed": patches_proposed,
        "lens_patches_accepted": patches_accepted,
        "correction_signals_path": str(sig_path),
        "lens_patches_path": str(patch_path),
    }


def list_signals(
    *,
    lens: Optional[str] = None,
    status: Optional[str] = "open",
) -> List[dict]:
    out: List[dict] = []
    for rec in _iter_jsonl(correction_signals_path()):
        if rec.get("event") != "correction_signal":
            continue
        if lens and rec.get("lens") != lens:
            continue
        if status and rec.get("status") != status:
            continue
        out.append(rec)
    return out


def list_patches(
    *,
    lens: Optional[str] = None,
    status: Optional[str] = None,
) -> List[dict]:
    out: List[dict] = []
    for rec in _iter_jsonl(lens_patches_path()):
        if lens and rec.get("lens") != lens:
            continue
        if status and rec.get("status") != status:
            continue
        out.append(rec)
    return out


def get_signal(signal_id: str) -> Optional[dict]:
    found: Optional[dict] = None
    for rec in _iter_jsonl(correction_signals_path()):
        if rec.get("id") == signal_id:
            found = rec
    return found


def get_patch(patch_id: str) -> Optional[dict]:
    found: Optional[dict] = None
    for rec in _iter_jsonl(lens_patches_path()):
        if rec.get("id") == patch_id:
            found = rec
    return found


def _load_signals(signal_ids: Sequence[str]) -> List[dict]:
    signals = []
    for sid in signal_ids:
        rec = get_signal(sid)
        if not rec:
            raise ValueError(f"unknown signal id {sid!r}")
        signals.append(rec)
    return signals


def _validate_propose_ops(signals: List[dict], ops: List[dict], *, force: bool) -> None:
    if len(signals) < 2 and not force:
        raise ValueError("propose requires ≥2 signal ids (or --force for one)")
    kinds = {s.get("kind") for s in signals}
    if kinds == {"noise"}:
        for op in ops:
            if op.get("op") == "add_check":
                raise ValueError(
                    "noise-only signals cannot add_check — use amend_check or add_guard"
                )
    lenses = {s.get("lens") for s in signals}
    if len(lenses) != 1:
        raise ValueError("signal ids must share one lens")
    cfg = resolve_config()
    lens_name = next(iter(lenses))
    _, lens_path = resolve_lens(cfg, lens_name)
    text = lens_path.read_text(encoding="utf-8")
    from .lens_parse import slug_markers_in_process

    known = slug_markers_in_process(text)
    for op in ops:
        if op.get("op") == "amend_check":
            slug = op["check"]
            if slug not in known:
                raise ValueError(
                    f"amend_check: no <!-- check: {slug} --> marker in lens file"
                )
        if op.get("op") == "add_check" and op.get("check"):
            if op["check"] in known:
                raise ValueError(f"add_check: slug {op['check']!r} already exists")


def propose_patch(
    *,
    lens: str,
    signal_ids: Sequence[str],
    ops: List[dict],
    force: bool = False,
    evidence_notes: Optional[List[str]] = None,
) -> dict:
    signals = _load_signals(list(signal_ids))
    _validate_propose_ops(signals, ops, force=force)
    cfg = resolve_config()
    lens_name, lens_path = resolve_lens(cfg, lens)
    if {s.get("lens") for s in signals} != {lens_name}:
        raise ValueError(f"signals lens mismatch (expected {lens_name!r})")
    if str(lens_path) != str(lens_path.resolve()):
        lens_path = lens_path.resolve()
    patch = {
        "id": _new_patch_id(),
        "status": "proposed",
        "lens": lens_name,
        "lens_path": str(lens_path),
        "ops": ops,
        "signal_ids": list(signal_ids),
        "evidence": {"notes": evidence_notes or [s.get("note", "") for s in signals]},
        "created_at": utc_now_iso(),
    }
    append_patch(patch)
    return patch


def preview_patch(patch_id: str) -> str:
    patch = get_patch(patch_id)
    if not patch:
        raise ValueError(f"unknown patch id {patch_id!r}")
    path = Path(patch["lens_path"])
    before = path.read_text(encoding="utf-8")
    after = apply_lens_ops(before, patch["ops"])
    return render_patch_diff(before, after, path)


def _rewrite_jsonl(path: Path, predicate, mutator) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    out: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        rec = json.loads(line)
        if predicate(rec):
            rec = mutator(rec)
            changed = True
        out.append(json.dumps(rec, separators=(",", ":"), ensure_ascii=False))
    if changed:
        path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return changed


def _mark_signals_actioned(signal_ids: Sequence[str], patch_id: str) -> None:
    wanted = set(signal_ids)

    def pred(rec: dict) -> bool:
        return rec.get("id") in wanted

    def mut(rec: dict) -> dict:
        rec = dict(rec)
        rec["status"] = "actioned"
        rec["linked_patch_id"] = patch_id
        return rec

    _rewrite_jsonl(correction_signals_path(), pred, mut)


def _append_patch_status(patch_id: str, status: str) -> None:
    patch = get_patch(patch_id)
    if not patch:
        raise ValueError(f"unknown patch id {patch_id!r}")
    updated = {**patch, "status": status}
    append_patch(updated)


def apply_patch(patch_id: str) -> Tuple[Path, dict]:
    patch = get_patch(patch_id)
    if not patch:
        raise ValueError(f"unknown patch id {patch_id!r}")
    if patch.get("status") != "proposed":
        raise ValueError(f"patch {patch_id!r} status is {patch.get('status')!r}, not proposed")

    cfg = resolve_config()
    lens_name, configured_path = resolve_lens(cfg, patch["lens"])
    patch_path = Path(patch["lens_path"]).resolve()
    if patch_path != configured_path.resolve():
        raise ValueError(
            f"lens path mismatch: patch targets {patch_path}, config has {configured_path}"
        )

    path = configured_path
    before = path.read_text(encoding="utf-8")
    after = apply_lens_ops(before, patch["ops"])
    path.write_text(after, encoding="utf-8")

    parsed = parse_lens_file(path)
    if not parsed.ok:
        path.write_text(before, encoding="utf-8")
        raise ValueError("apply would break lens shape: " + "; ".join(parsed.errors))

    _mark_signals_actioned(patch.get("signal_ids") or [], patch_id)
    accepted = {**patch, "status": "accepted"}
    append_patch(accepted)
    return path, accepted


def ensure_correction_logs() -> Tuple[Path, Path]:
    sig = ensure_log(correction_signals_path())
    pat = ensure_log(lens_patches_path())
    return sig, pat
