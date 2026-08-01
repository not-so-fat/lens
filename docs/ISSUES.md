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

## Remaining (not code bugs)

### I-1 residual — host contract

If `afterFileEdit` omits workspace **and** `stop` uses a different conversation id than edit, enforcement still silently passes. Mitigation: host contract in README + stderr warning. Options (b)/(c) rejected for MVP (cross-talk / incomplete without (a)).

### I-4 — live Cursor desktop E2E

Not automatable from unittest. Manual smoke in README (“Manual Cursor smoke”). Run once after install before calling Cursor support verified.
