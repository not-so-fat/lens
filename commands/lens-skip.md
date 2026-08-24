---
name: lens-skip
description: Record a lens_skip so the Stop-hook loop clears without a review — only when the owner deliberately held.
---

Append a `lens_skip` record to the configured run log (`log_path`). This is the
loop's **second exit**: the owner told you to hold a deliverable rather than run
the lens. It is recorded (never a silent skip) and clears the Stop-hook gate for
this session, exactly the way a `lens_run` does.

Use this **only** when the owner explicitly said to hold / not now / skip. If you
are simply done, run the `lens` agent instead.

Usage from the user:

```text
/lens-skip "<deliverable>" [reason]
```

Parse the arguments, then run (the session id is the one named in the Stop-hook
block message):

```bash
PYTHONPATH="<plugin-root>/python" python3 -m lens_lib skip "<deliverable>" \
  --session "<session id>" [--reason "<why held>"]
```

- `deliverable` is a stable key (reuse the same one the lens run would have used).
- `--session` should be the current session id so the gate clears for this chat.
- Show the appended JSON and the log path.
- Do not invent a skip the owner did not ask for.
