#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook — arm the session on explicit lens invocation (F3.5).

A chat deliverable never writes a watched file, so "use <lens>" cannot be
caught by the write-triggered Stop gate. When the user explicitly asks for the
lens, arm the session; the Stop hook then blocks until a lens_run (or a
lens_skip, if the owner holds) is logged.
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
    if not session:
        tp = payload.get("transcript_path") or payload.get("transcriptPath")
        if tp:
            session = Path(tp).stem

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
        # stdout from a UserPromptSubmit hook is added to the agent's context.
        print(
            "[lens] Explicit lens invocation detected. Before ending this turn you "
            "MUST run the `lens` agent on the deliverable and log a lens_run for "
            "this session (include \"session\"), or record a lens_skip if the owner "
            "told you to hold; otherwise the Stop hook will block until one is logged."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
