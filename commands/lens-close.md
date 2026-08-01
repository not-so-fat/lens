---
name: lens-close
description: Record a human_review line for a deliverable after the owner finishes review.
---

Append a `human_review` record to the vault run log.

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
- Show the appended JSON and the log path. On refusal, show the error and do not invent a record.
