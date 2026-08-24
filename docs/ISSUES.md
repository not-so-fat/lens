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

**Remaining narrow trade-off:** untagged in-window runs are forgiven and remain the one cross-session vector (a concurrent Claude session’s untagged `lens_run` can satisfy this one). Tag runs (`append-run --session`) to close it fully. Cursor still requires a session tag — omit `--session` and a real review still blocks (by design; agent/CLI instructions hold that line).

## Remaining (not code bugs)

### I-1 residual — host contract

If `afterFileEdit` omits workspace **and** `stop` uses a different conversation id than edit, enforcement still silently passes. Mitigation: host contract in README + stderr warning. Options (b)/(c) rejected for MVP (cross-talk / incomplete without (a)).

### I-4 — live Cursor desktop E2E

Not automatable from unittest. Manual smoke in README (“Manual Cursor smoke”). Run once after install before calling Cursor support verified.

### I-7 — chat-scoped gate (Claude) / write-batch after last run (Cursor)

- **Claude (F3.1):** still session-window (`ts ≥` transcript first-event) — one early `lens_run` can clear later writes in the same transcript. Deliverable keys not required.
- **Cursor:** side-channel writes **after** the latest session-tagged `lens_run` are enforced again; consumed lines are pruned. Closes the “second deliverable in same chat slips” hole for Cursor without full deliverable-key plumbing.

Full deliverable-key scoping on both hosts remains optional post-pilot.

### I-9 — explicit lens invocation on a chat deliverable is now enforced (was: unenforced)

The write-triggered Stop gate only fires on writes to `watch_globs` files. A deliverable produced **in the chat** (analysis, comparison, summary — no file written) does not trip it. That is fine for passive coverage, but it broke an **explicit** request: when the user typed *"use yusuke lens"* on a chat task, nothing enforced it — the loop fell back to convention (the agent voluntarily complying), which is exactly what F3 exists to replace.

Verified live (session `9b1ecf4e-edf5-4a40-be0c-85f3155dc075`, run log):

- Chat-research turns 04:04–04:28 — `wrote_watched=false`, nothing blocked. The user asked *"use Yusuke lens"* / *"Redo research with yusuke lens"* here; nothing ran (the reported "lens is not working").
- Once a markdown deliverable was written (04:39) the write gate **did** engage: `blocked=true` at 04:39 and 04:44, a `lens_run` logged at 04:45, then `blocked=false`. So the write path worked — the gap was strictly the chat phase, where an explicit invocation had no enforcement hook.

**Fix (this release, Claude Code): arm-on-explicit-invocation.** A `UserPromptSubmit` hook (`python/claude_user_prompt.py`) detects an explicit, **affirmative** request (`use`/`run`/`apply`/`using`/`with <lens>`, `lens=<name>`, `run the lens`, or a configured lens name) and **arms** the session (`~/.lens/sessions/<session>/armed.txt`). The detector rejects negations/hedges (`don't use the lens`, `without using the lens`, `use my eyeglasses lens metaphor`). `run_check` (shared by both hosts) then blocks an armed session until a `lens_run` is logged **regardless of watched writes**, and disarms once one lands. `hook_check` gains an `armed` field. So an explicit opt-in is a hard gate for chat deliverables too — no separate manual command to remember (that would be the same convention trap).

**Cursor: not yet armed (follow-up).** `run_check` already honors `armed`, but only Claude's `UserPromptSubmit` writes the marker. Cursor arming needs a `beforeSubmitPrompt` entry mirroring `claude_user_prompt.py`; deferred until it can be verified on the desktop IDE (cf. I-4). Until then, Cursor enforces only the write-triggered gate.

**Still by-spec:** a chat deliverable with **no** explicit invocation is not auto-enforced (the write gate can't see it, and firing the lens on every Stop is noisy). Passive coverage of chat work stays a post-pilot question. Related blind spot unchanged: files written via a **Bash redirect / `tee`** are invisible to `written_paths_from_transcript` (structured `Write`/`Edit`/`NotebookEdit` only).

### I-10 — the loop's missing second exit (was: circuit breakers faking it)

**Root cause.** The Stop-hook loop had exactly one exit — a logged `lens_run`. But an obligation has *two* legitimate ends: the review happened, **or** the owner deliberately held it. With no representation for "held," a session where the owner said *"hold, don't run the lens"* could only escape by satisfying the gate — so the loop re-blocked every stop until a harness-level cap force-broke it (observed: 9 consecutive blocks; a comment recorded one arm blocking 92× in 10 min). The response had been to bolt on stateful **circuit breakers** (`ARM_MAX_BLOCKS`, a watched-block counter), **TTLs**, and **warn-first** escalation — a growing pile of machinery, each piece a crude reconstruction of the one missing concept.

**Fix.** Give the loop its real second exit: a **`lens_skip`** record (§7.2b, `/lens-skip`). `run_check` now treats the gate as satisfied by a `lens_run` **or** a `lens_skip` for the session — for both the write gate and the arm gate. With a recorded, intentional "hold" available, all the breakers/TTLs/warn-first were **deleted**: the loop keeps looping until one of two real things happens, and never wedges because the owner always has a one-command exit. A skip is *recorded*, so this is not a silent skip — it is an accountable one.

**Also:** Claude's Stop hook now blocks via `{"decision":"block","reason":…}` (exit 0), the same structured form Codex uses, so enforcement surfaces as *feedback* rather than a "Stop hook error." Arming (I-9) is unchanged in intent but reuses this same two-exit loop instead of its own breaker/TTL.
