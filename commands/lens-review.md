---
name: lens-review
description: Run the configured lens on a deliverable the Stop hook cannot auto-detect — a chat answer, or a file written via Bash — then log the lens_run. Manual trigger; does not block. Enforcement stays write-triggered.
---

The Stop-hook gate only fires on writes to `watch_globs` files, so a deliverable produced **in the chat** (an analysis, comparison, summary) — or a file written through a Bash redirect rather than the Write tool — is never enforced. Use this to run your lens on such a deliverable **on demand** and record the run.

Usage from the user:

```text
/lens-review "<deliverable-key>" [lens=<name>] [files=<path> ...]
<optionally paste the deliverable text here>
```

Steps:

1. Assemble the deliverable: the pasted text and/or the files listed.
2. Invoke the `lens` agent (round 1) with `lens=<name, or omit for default_lens>`, `deliverable="<deliverable-key>"`, the inline content and/or `files=[...]`. Run the produce → lens → fix loop as usual until a round is terminal (verdict PASS, or every finding ESCALATE).
3. On the terminal round, append the `lens_run` the agent emits (from the plugin root):

   ```bash
   PYTHONPATH="<plugin-root>/python" python3 -m lens_lib append-run \
     --host claude-code --session "<this session id, if known>" --json '<LENS_LOG_APPEND json>'
   ```

4. Reuse the same `<deliverable-key>` with `/lens-close` after your own review, so the `human_review` line joins this `lens_run`.

Notes:

- This does **not** block the turn — it is a *voluntary* review for deliverables the Stop hook cannot see. It does not change enforcement, which remains write-triggered (a chat turn is never forced through the lens).
- `--session` is best-effort here (there is no gate to satisfy for a chat deliverable); include it when known so the run joins this session in the log.
- Automatic enforcement of chat deliverables (turn-based, or a "is this a deliverable" heuristic) is an open question — see [`docs/ISSUES.md`](../docs/ISSUES.md) **I-9**.
