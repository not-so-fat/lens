---
name: lens-doctor
description: Validate Lens config, lens file shape, run log, and host hooks. Fixes Cursor sandbox readonly path for the lens file directory.
---

Run the Lens doctor against this machine.

1. Resolve the plugin root (repo or `$CLAUDE_PLUGIN_ROOT` / Cursor plugin path).
2. Execute:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor
```

Optional: write config in one step:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor \
  --write-lens "/absolute/path/to/your-lens.md" \
  --write-log "/absolute/path/to/lens_runs.jsonl"
```

Report every `[PASS]` / `[FAIL]` line to the user. If any check fails, stop and tell them how to fix it (see `README.md` and `docs/PRD.md`).
