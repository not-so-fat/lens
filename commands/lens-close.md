---
name: lens-close
description: Record a human_review line for a deliverable after the owner finishes review.
---

Append a `human_review` record to the configured run log (`log_path`).

Usage from the user:

```text
/lens-close "<deliverable>" corrections=<n> [misses…] [noise…]
```

Parse the arguments, then run:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib close "<deliverable>" --corrections <n> \
  [--miss "check:note" ...] [--noise "check:note" ...]
```

- `deliverable` must match an existing `lens_run` key (command refuses otherwise).
- `misses` / `noise` items are `check:note` pairs (kebab-case check slug).
- Each miss/noise appends a durable `correction_signal` to `~/.lens/correction_signals.jsonl` (see `docs/PRD_CORRECTION_CAPTURE.md`).
- Show the appended JSON and the log path. On refusal, show the error and do not invent a record.
- If signals were captured, stderr lists their `cs_…` ids.

## Curation rail (owner)

After repeated misses accumulate:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections list --lens <name>
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections propose \
  --lens <name> --signal-ids cs_a,cs_b --ops-file ops.json [--preview]
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib corrections apply lp_…
```

`ops.json` is a JSON array of `add_check`, `amend_check`, or `add_guard` ops. Noise-only signals must not use `add_check` (use guard/amend). Human `apply` writes the lens file; run `/lens-doctor` after.
