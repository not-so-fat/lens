#!/usr/bin/env python3
"""Codex UserPromptSubmit hook — arm the session on explicit lens invocation.

Parity with the Claude arming hook: a chat deliverable never writes a watched
file, so "use <lens>" can't be caught by the write gate. When the user
explicitly asks for the lens, arm the session; the Stop hook then warns and, on
a later unsatisfied stop, blocks until a lens_run is logged (warn-first,
self-clearing via the shared circuit breaker + TTL).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lens_lib.check import arm_session, is_lens_invocation  # noqa: E402
from lens_lib.config import ConfigError, list_lens_names, resolve_config  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    prompt = (
        payload.get("prompt")
        or payload.get("user_prompt")
        or payload.get("userPrompt")
        or ""
    )
    session = payload.get("session_id") or payload.get("sessionId")

    names = ()
    try:
        names = tuple(list_lens_names(resolve_config()))
    except ConfigError:
        names = ()

    if session and is_lens_invocation(prompt, names):
        try:
            arm_session(str(session))
        except OSError:
            return 0  # could not arm — do not claim the Stop hook will block
        print(
            "[lens] Explicit lens invocation detected. Before ending this turn you "
            "MUST run the `lens` agent on the deliverable and log a lens_run for "
            "this session (include \"session\"); otherwise the Stop hook will warn "
            "and then block on a later stop until a lens_run is logged."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
