---
name: lens-doctor
description: Validate Lens config, vault, lens shape, run log, and host hooks. Fixes Cursor sandbox readonly path for vault_root.
---

Run the Lens doctor against this machine.

1. Resolve the plugin root (repo or `$CLAUDE_PLUGIN_ROOT` / Cursor plugin path).
2. Execute:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor
```

Optional: write config in one step:

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib doctor --write-config "/absolute/path/to/vault"
```

Report every `[PASS]` / `[FAIL]` line to the user. If any check fails, stop and tell them how to fix it (see `README.md` and `docs/PRD.md` F4.3).
