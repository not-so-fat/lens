---
name: lens-doctor
description: Validate Lens config, named lenses, run log, and host hooks. Fixes Cursor sandbox readonly paths for lens directories.
---

Run the Lens doctor against this machine.

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor
```

Bootstrap config with one named lens:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor \
  --write-log "/absolute/path/to/lens_runs.jsonl" \
  --write-lens-name "review" \
  --write-lens-path "/absolute/path/to/review.md"
```

Manage names later: `python3 -m lens_lib lens add|list|remove`.

Report every `[PASS]` / `[FAIL]` line to the user.
