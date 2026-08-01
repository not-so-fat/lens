# Open issues / redesign risks

Tracked gaps from Cursor/Claude hook regression work. Decisions below reflect 2026-08-01 design review.

## Fixed in-tree (regression-covered)

1. **Cursor stop thin payload** — `afterFileEdit` side-channel required.
2. **Session field-name drift** — fan-out across `session_id` / `conversation_id` (conversation_id preferred).
3. **I-2 relative hook cwd** — `${CURSOR_PLUGIN_ROOT}/python/...` (Claude: `${CLAUDE_PLUGIN_ROOT}`).
4. **I-3 per-conversation keys** — side-channel primary key `(workspace, conversation_id)`; workspace-wide fallback **only** when id is missing/`unknown`. `hook_check` logs `session_ids`.
5. **I-5 loop_limit UX** — unlock hint; last follow-up warning; `hook_limit_exhausted`. README § Unlocking.
6. **I-6 doctor consistency** — validates PLUGIN_ROOT vars and expanded scripts exist.
7. **I-1 warning** — `afterFileEdit` stderr warns when workspace root is absent.
8. **P1 unbounded Cursor gate** — `has_lens_run_since(None)` no longer matches any historical run; side-channel lines are `ts\\tpath` so Cursor gets a write-time window; optional `session` / `session_ids` on `lens_run` as backup. Covered by `test_cursor_stale_lens_run_does_not_unblock_fresh_conversation`.
9. **Runner drift (#9)** — Claude/Cursor agent files stay separate (host Logging differs); must-match spans use `<!-- SHARED:… -->` markers and `tests/test_runner_consistency.py`. See [`docs/RELEASE.md`](RELEASE.md).
10. **Cursor gate is session-scoped only** — no global `has_lens_run_since` on the no-transcript path (cross-chat leak). M3 join key is `wrote_watched` + `blocked=false`, not `watched_writes∧lens_run_found`.

### I-8 — Claude global time gate — fixed

Both hosts session-scope the gate. Claude also **forgives untagged** in-window `lens_run`s (Bash append footgun) but rejects runs tagged for another session. Claude Stop always has a session id (payload or transcript stem) — no separate global time-gate branch. Prefer `append-run --session`. Regressions: `test_claude_newer_other_session_run_does_not_leak`, `test_claude_untagged_lens_run_still_satisfies`.

## Remaining (not code bugs)

### I-1 residual — host contract

If `afterFileEdit` omits workspace **and** `stop` uses a different conversation id than edit, enforcement still silently passes. Mitigation: host contract in README + stderr warning. Options (b)/(c) rejected for MVP (cross-talk / incomplete without (a)).

### I-4 — live Cursor desktop E2E

Not automatable from unittest. Manual smoke in README (“Manual Cursor smoke”). Run once after install before calling Cursor support verified.

### I-7 — chat-scoped gate (Claude) / write-batch after last run (Cursor)

- **Claude (F3.1):** still session-window (`ts ≥` transcript first-event) — one early `lens_run` can clear later writes in the same transcript. Deliverable keys not required.
- **Cursor:** side-channel writes **after** the latest session-tagged `lens_run` are enforced again; consumed lines are pruned. Closes the “second deliverable in same chat slips” hole for Cursor without full deliverable-key plumbing.

Full deliverable-key scoping on both hosts remains optional post-pilot.
