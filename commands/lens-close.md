---
name: lens-close
description: Record a human_review line for a terminal lens_run after the owner finishes review.
---

Append a `human_review` record to the configured run log (`log_path`), tied to a specific terminal `lens_run`.

Usage from the user:

```text
/lens-close --run-id <lr_…> corrections=<n> [misses…] [noise…]
/lens-close "<deliverable>" corrections=<n>   # only when unambiguous
```

Parse the arguments, then run:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib close \
  [--run-id <lr_…>] ["<deliverable>"] --corrections <n> \
  [--lens <name>] [--session <id>] \
  [--miss "check:note" ...] [--noise "check:note" ...]
```

- Prefer `--run-id` from the append launcher stderr (`lens_run_id: lr_…`) after a terminal review — deliverable is optional then.
- Deliverable-only close works when exactly one `lens_run` exists for that key; otherwise the command lists candidates and refuses (NOT-42).
- Disambiguate with `--lens` and/or `--session` when two runs share a deliverable key.
- `misses` / `noise` items are `check:note` pairs (kebab-case check slug). Do not infer miss/noise from edits alone.
- Each miss/noise appends a durable `correction_signal` to `~/.lens/correction_signals.jsonl` (see `docs/PRD_CORRECTION_CAPTURE.md`).
- Show the appended JSON and the log path. On refusal, show the error and do not invent a record.
- If signals were captured, stderr lists their `cs_…` ids.

List candidate runs when ambiguous:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib runs list --deliverable "<key>"
```

Flywheel counts:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections funnel
```

## Curation rail (owner)

After repeated misses accumulate:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections list --lens <name>
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections propose \
  --lens <name> --signal-ids cs_a,cs_b --ops-file ops.json [--preview]
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections apply lp_…
```

`ops.json` is a JSON array of `add_check`, `amend_check`, or `add_guard` ops. Noise-only signals must not use `add_check` (use guard/amend). Human `apply` writes the lens file; run `/lens-doctor` after.
