#!/usr/bin/env python3
"""Lens-run append launcher for the Claude Code runner.

Invoked as ``python3 "${CLAUDE_PLUGIN_ROOT}/python/lens_append.py" …`` — a bare
`python3 <path>` form with **no leading `PYTHONPATH=` assignment**. That matters
for a background reviewer subagent: Claude Code's Bash allow-rules don't match
past an env-var assignment (`PYTHONPATH` is not on its known-safe strip list), so
a `PYTHONPATH=… python3 -m lens_lib …` invocation would auto-deny with no prompt.
Bootstrapping `sys.path` here (as `claude_stop.py` / `claude_user_prompt.py`
already do) lets the append run under a stable, pre-grantable command.

Forwards its arguments verbatim to the `append-run` CLI subcommand.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.__main__ import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["append-run", *sys.argv[1:]]))
