---
created: 2026-07-31
updated: 2026-08-01
status: refining
---

# Lens — personal review standards for AI agents (product idea + plugin PRD)

> **Canonical home:** this file is `docs/PRD.md` in the lens plugin repo. Contracts in `contracts/` must match §7. As-built notes that supersede earlier draft wording are folded into the Req tables below (dual marketplace packaging; named multi-lens config; no Lexicon vault/`area` concepts).

> **One-line:** professionals working with AI agents spend their review time on issues that are simple *for them*; a lens — their review standards as a runnable, versioned file — lets agents resolve those issues among themselves before human review, and turns every correction into a permanent standard instead of a repeated conversation.

## Decision

**Pursue.** Next action: one private repo carrying the Claude Code plugin **and Cursor support**, installed on both laptops — the deployment itself is the MVP test (implementation spec: the plugin PRD below). Codex is evaluated but out of scope (Appendix B). The deck card comes after, gated on `human_review` pilot data. No standalone product (rationale in Positioning).

## Problem

- Agent output volume outruns human review capacity, and review is where leverage dies ([[Sources/Ideas/personal/2026-07-25 AI Leverage Benchmark — Verification Is the Bottleneck]]).
- Most review findings are simple for the reviewer — the agent just doesn't share their priorities, boundaries, or standards. Measured personally: ~12 correction rounds ≈ one restated ask (baseline in the owner lens).
- Corrections don't compound: the most-repeated correction was given 5+ times across separate sessions (taste extraction: 23 sessions, ~180 feedback moments).
- The standards exist — but in one person's head, restated one correction at a time, siloed per host (Claude Code, Cursor, Codex) and per machine; every new session starts from zero.

## Why existing tools don't cover it

- Code-review bots (CodeRabbit, Claude PR review, Bugbot) check generic defects. They don't know this person's boundaries ("rating is my job"), argument standards (problem before solution), or audience rules (don't spend recognition budget on consensus) — which is where the correction rounds actually go.
- Agent memory features recall passively; nothing enforces a review before a deliverable reaches the human.

## Evidence the mechanism works (two days, measured)

- 16 real deliverables ran produce → lens review → fix loops: 109 findings, 105 resolved agent-to-agent (37 as whole-class fixes), and the human saw only 2 escalations + 2 disputes. 15 of 16 loops closed in 2–3 rounds. (Run log: owner-chosen `log_path`, records through 2026-07-31T20:02Z, newest record per deliverable.)
- The two verification directions have different economics — truth checks run autonomously and catch what humans can't audit at scale; taste converges only through corrections promoted into the lens ([[Sources/Ideas/personal/2026-07-30 Task-Specific Lenses — Product Insight from the Half-Year Review Session]]).
- Bootstrapping is cheap: mining 23 sessions of existing history produced 6 new lens criteria in one pass ([[Sources/Ideas/personal/2026-07-31 Taste profile — extracted from session history]]). Onboarding = mine the user's own history, not ask them to write rules from scratch.

## Product shape — each piece maps to an observed need

| Piece | Observed need it answers |
| --- | --- |
| **Named lens files** — versioned review protocols, human-owned, one or more names per machine (`lenses` / `lenses_dir`) | corrections repeated 5+ times because they had nowhere to live; different task families need different standards |
| **Runner** — reviewer agent that executes the lens in a loop until pass or escalate | 105 of 109 findings resolved without the human |
| **Correction capture** — live corrections and history mining become proposed criteria | taste is not discoverable by the reviewer; it converges via feedback |
| **Run log + analytics** — every run recorded, joined with the human's final review | retrospective and log disagreed (15/13 recalled vs 14/11 logged at the time); only the log made the discrepancy detectable and resolvable |
| **Multi-host enforcement** — plugin/hooks per host, lens fetched from one source | v0's review loop is a remembered convention — recorded as the known gap in the experiment brief |

## Deployment path (personal need first)

1. **Now:** file-based v0 — lens as a local markdown file, runner as a local agent file, one laptop.
2. **Next: one private repo — Claude Code plugin + Cursor plugin** — any laptop, one install per host; named lenses configured in `~/.lens/config.json`. Spec: the plugin PRD below.
3. **Then:** lens as an Agent Deck card — per-business lens switching via deck binding; Codex reached through the existing deck MCP + stub machinery (feasibility evaluated below).

## Positioning

Agent Deck is context switching; a lens is judgment that must travel with that context — a natural deck card type, not a third product. agent-dealer automates the same gate for queued/unattended work. A standalone product only becomes worth considering if deck distribution fails (hosts without Deck, non-agent surfaces).

## Cursor & Codex feasibility (evaluated 2026-08-01)

| Capability the loop needs | Cursor | Codex |
| --- | --- | --- |
| Reviewer with fresh context | YES — subagents: `.cursor/agents/` (project) or `~/.cursor/agents/` (user), `readonly: true`, own context window ([docs](https://cursor.com/docs/subagents)) | YES on CLI/desktop — subagents: `~/.codex/agents/*.toml`, read-only sandbox, fresh session ([docs](https://learn.chatgpt.com/docs/agent-configuration/subagents)) |
| Lens from filepath or MCP | YES, one config step — `sandbox.json` `additionalReadonlyPaths`, or MCP ([sandbox](https://cursor.com/docs/reference/sandbox), [MCP](https://cursor.com/docs/mcp)) | YES — file reads unrestricted by sandbox ([config](https://learn.chatgpt.com/docs/config-file/config-advanced)); MCP config shared across CLI/desktop/IDE ([MCP](https://learn.chatgpt.com/docs/extend/mcp)) |
| Blocking enforcement at turn end | YES on desktop IDE — `stop` hook returns `followup_message`, bounded forced continuation (`loop_limit`, default 5); hooks GA, config at `~/.cursor/hooks.json` (user) or project ([docs](https://cursor.com/docs/hooks)) | YES on CLI/desktop — `Stop` hook `{"decision": "block"}` re-prompts until satisfied ([docs](https://learn.chatgpt.com/docs/hooks)) |
| JSONL append to the run log | YES — hook scripts run outside the sandbox ([hooks](https://cursor.com/docs/hooks)); agent writes need `additionalReadwritePaths` ([sandbox](https://cursor.com/docs/reference/sandbox)) | YES — `writable_roots` config ([config](https://learn.chatgpt.com/docs/config-file/config-advanced)), or hook-side append ([hooks](https://learn.chatgpt.com/docs/hooks)) |

**Verdict: the loop ports to both hosts with native primitives — feasibility does not depend on the deck.** Remaining gaps: per-surface — Cursor CLI hook delivery is documented-limited ([hooks](https://cursor.com/docs/hooks)) and reported unreliable ([forum report](https://forum.cursor.com/t/cursor-cli-doesnt-send-all-events-defined-in-hooks/148316)); Codex IDE-extension hooks are undocumented ([IDE docs](https://learn.chatgpt.com/docs/codex/ide)) — and one per-host design limit: Cursor's stop gate is bounded continuation (`loop_limit`, default 5), not a hard block. The bounded gate is accepted: 15 of 16 observed loops closed within 3 rounds (Evidence above). The deck card's value is therefore lens distribution/switching, not feasibility.

## Open questions — marked by what each blocks

- **Blocks the deck card** — lens body's home: deck card vs local file (one source of truth — the no-mirroring rule forces a choice).
- **Resolved for the plugin release by exclusion (§10); reopens at the deck card** — per-surface enforcement gaps: Cursor CLI (hook delivery unreliable) is excluded from the plugin release; the Codex IDE extension (hooks undocumented) remains a deck-card question; the run log's skip rate is the evidence to collect.
- **Shapes the plugin step, worth arguing** — privacy: lenses encode work context; multi-laptop sync must stay private (private repo suffices? deck sync changes the answer).
- **Blocks nothing yet** — team lenses: can a team share standards the way one person does, and who reviews the reviewer?
- **Shapes the plugin's coverage, worth arguing** — enforcement scope: the Stop-hook gate is write-triggered. An **explicit** request (*"use yusuke lens"*) on a chat deliverable is now enforced via `UserPromptSubmit` arming (see [`docs/ISSUES.md`](ISSUES.md) I-9). Still open: **passive** coverage of chat work the user did not explicitly flag — firing the lens on every Stop is noisy, so pilot skip data is the evidence to collect. Files written via Bash (not the Write tool) also remain invisible.

Implementation residuals from Cursor hook regression work (session-id / workspace side-channel, relative hook cwd, live desktop E2E): see [`docs/ISSUES.md`](ISSUES.md).

---

# Plugin PRD — multi-laptop, Claude Code + Cursor

Implementation half (scaffold: pb_prd_scaffold). Everything above is the framing; a coding agent builds from here. Stage naming across this document: **v0 loop** (file-based, running today) → **plugin release** (this PRD: Claude Code plugin + Cursor support) → **deck card** (gated, see Decision).

## 1. Product overview

Scope: package the proven v0 loop (runner agent + named lens files + run log) into one private repo that installs on any machine — a Claude Code plugin (`.claude-plugin/`) and a Cursor plugin (`.cursor-plugin/`, **desktop IDE**; the CLI surface is excluded, §10) sharing config, contracts, and the run log — so the loop cannot be silently skipped on either host's covered surface. Codex: out of scope, port sketch in Appendix B.

**Success criteria (evaluated at M3 — seven days after hook activation):** plugin installed and passing `/lens-doctor` on 2 laptops; Stop-hook enforcement active on both hosts (Cursor: desktop IDE); ≥ 90% of `hook_check` records with `enforce=true` and `wrote_watched=true` also have `blocked=false` (§7.6, measurement window per §9, min 10 such records, both hosts pooled — Cursor prune means `watched_writes∧lens_run_found` is the wrong join); ≥ 1 `lens_run` logged from Cursor (`host: "cursor"`); ≥ 5 deliverables carry `human_review` lines.

## 2. Target users & roles

Primary persona: a product lead who produces documents, decks, and specs through coding agents on multiple machines and is the only reviewer of record.

| Role | Goal | Plugin surface |
| --- | --- | --- |
| Lens owner (human) | Standards enforced everywhere; final review only | named lenses in `~/.lens/config.json`; `/lens-close`; `/lens-doctor`; `lens add\|list\|remove` |
| Worker agent | Pass the lens loop before surfacing a deliverable | `lens` subagent invocation contract (§7.3), Claude Code and Cursor |
| Runner (`lens` subagent) | Execute a named lens; report FIX/ESCALATE/PASS; log terminal rounds | `agents/lens.md` (Claude Code) / `agents/cursor/lens.md` (Cursor) + run log (§7.1) |

"I am a product lead / I want my correction standards enforced by agents themselves / I use Lens because corrections that don't compound cost me the ~12-round baseline (Problem, above)." Voice rules: use *lens, runner, worker, finding, run* — never introduce a synonym; "buddy" is allowed as informal alias in prose, never in contracts.

Deferred roles (team members, Codex host): see §10.

## 3. User stories (testable)

**US-1 (plugin). Install on a new laptop.** As a lens owner, I want one-command install so my standards travel.
Acceptance:
- [ ] `claude plugin marketplace add <private-repo>` + `claude plugin install lens` succeeds on a clean machine with repo access
- [ ] a new session lists the `lens` agent
- [ ] `/lens-doctor` exits green after writing `~/.lens/config.json` with named `lenses` (or `lenses_dir`), `default_lens`, and `log_path`

**US-2 (plugin). Run the loop.** As a worker agent, I want to invoke the runner with a lens **name** (plus round, deliverable key, files, prior findings) and get a verdict so simple issues resolve without the human.
Acceptance:
- [ ] runner reply contains verdict `PASS`/`FIX`/`ESCALATE` and findings matching §7.3 output shape
- [ ] every finding cites a `check` slug from the lens vocabulary (F2.3)
- [ ] omitting `lens` uses config `default_lens`
- [ ] with an unknown lens name or unreadable lens file, runner replies `LENS UNAVAILABLE: <name or path>` and produces no findings

**US-2b (plugin). Manage named lenses.** As a lens owner, I want to register multiple lenses once (or gradually) and invoke them by name.
Acceptance:
- [ ] `~/.lens/config.json` supports `lenses` (name → absolute path) and optional `lenses_dir` (§7.4)
- [ ] `python -m lens_lib lens add|list|remove` updates / lists the map
- [ ] a name present only as `<lenses_dir>/<name>.md` resolves without a map entry
- [ ] logged `lens_run.lens` is the **name**, not the file path

**US-3 (plugin). Enforcement.** As a lens owner, I want a turn that wrote watched files blocked at its Stop-hook firing until a lens run is logged, so the loop cannot be silently skipped.
Acceptance:
- [ ] the Stop-hook firing blocks (exit 2, message names the missing step) when the session has written files matching `watch_globs` (fnmatch against cwd-relative and absolute paths; never `~/.claude/` or system temp — §7.4) and the log has no same-session `lens_run` with `ts` ≥ the transcript's first-event time
- [ ] the firing passes when such a `lens_run` exists, when no watched files were written, or when `enforce=false`
- [ ] (Claude Code) an explicit lens invocation in the prompt (`use <lens>`, `lens=<name>`, `run the lens`; negations do not count) **arms** the session, requiring a same-session `lens_run` **even with no watched writes** (§7.6 `armed`); it disarms once one lands. Because a prompt-text arm is a heuristic, enforcement is warn-first: the first unsatisfied stop only warns (`skip_reason=arm_warned`) and a later unsatisfied stop blocks, so a genuine arm that runs the lens after the warning never blocks. An unsatisfied arm is self-clearing — a 3-block circuit breaker (`arm_abandoned`) and a 2 h TTL (`arm_expired`) — so a false/abandoned arm can't wedge a session (I-9 hardening). Cursor arming is a follow-up (I-9)
- [ ] every firing appends a `hook_check` record (§7.6)
- [ ] false-block rate meets NFR-3 (evaluated at M3, over the §9 window)

**US-4 (plugin). Every run recorded.** As a lens owner, I want one JSONL line per run so I can analyze checks, reactions, and rounds.
Acceptance:
- [ ] terminal rounds append exactly one line validating against §7.1
- [ ] `ts` comes from the system clock (never model-estimated)
- [ ] a reopened loop logs cumulatively (full history, higher `rounds`)

**US-5 (plugin). Close the loop.** As a lens owner, I want to record my final review in one command.
Acceptance:
- [ ] `/lens-close "<deliverable>" corrections=<n> [misses…] [noise…]` appends a line validating against §7.2, joining an existing `lens_run` deliverable key

**US-6 (plugin). Same loop in Cursor.** As a lens owner, I want the identical loop and enforcement when I work in Cursor's desktop IDE (the CLI surface is excluded — §10).
Acceptance:
- [ ] Cursor plugin install (Team Marketplace / local import of `.cursor-plugin/`) loads the lens subagent and `stop` / `afterFileEdit` hooks; `/lens-doctor` validates both (F5.3)
- [ ] the Cursor subagent reviews per §7.3 and logs per §7.1 with `host: "cursor"`
- [ ] the Cursor `stop` hook returns `followup_message` when watched writes lack a session `lens_run` (bounded by `loop_limit`; F5.2) and appends `hook_check` with `host: "cursor"`
- [ ] configured lens directories are readable from the Cursor sandbox (`sandbox.json` `additionalReadonlyPaths`, written/merged by `/lens-doctor`; F5.3)

Deferred stories (deck card fetch, Codex host, correction-capture automation): see §10.

## 4. Features & requirements

### F1 — Plugin packaging & config

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F1.1 | Private git repo is a dual marketplace: `.claude-plugin/marketplace.json` + `.cursor-plugin/marketplace.json`, each offering plugin `lens` with agents, hooks, commands | US-1 / US-6 install paths pass on macOS |
| F1.2 | Config is `~/.lens/config.json` (§7.4): named `lenses` and/or `lenses_dir`, `default_lens`, `log_path`; env `LENS_LOG_PATH` / `LENS_DEFAULT` override log path / default name → else error with setup instructions | `/lens-doctor` reports source, default, and known names |
| F1.3 | All hook/command scripts are Python 3 stdlib-only | `grep`-verifiable: no third-party imports |
| F1.4 | Named-lens management CLI: `python -m lens_lib lens add\|list\|remove` | US-2b acceptance |

### F2 — Runner agent

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F2.1 | Plugin ships runners as `agents/lens.md` (Claude Code) and `agents/cursor/lens.md` (Cursor), semantics identical to the proven v0 agent with hard-coded paths replaced by name→path resolution (F1.2) | US-2 acceptance |
| F2.2 | Runner resolves lens **name** → file path (`lenses` map, else `lenses_dir/<name>.md`) at invocation time; that file is the single source of truth (input shape §7.5) | editing the lens file changes the next run's checks with no plugin change; switching names selects a different file |
| F2.3 | The bundled check-slug vocabulary lives in the runner agent file; a new slug is minted only when a finding fires on a check with no slug in the list — whether newly added to the lens or previously uncovered — after grepping the run log for an existing one | no two slugs for one lens question across the pilot log |
| F2.4 | Terminal-round logging per §7.1 (`lens` = name); non-terminal rounds never log | US-4 acceptance |

### F3 — Enforcement (Stop hook)

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F3.1 | The Stop hook fires at each turn end with the session transcript path; it detects session writes matching `watch_globs` (§7.4 matching rules) and checks `log_path` for a `lens_run` tagged with this session (or conversation) id and `ts` ≥ the transcript's first-event time. When the session was **armed** by an explicit lens invocation (F3.5) and no same-session `lens_run` has been logged since the arm, it warns on the first unsatisfied stop and blocks on a later one (warn-first, F3.5) | US-3 acceptance |
| F3.5 | (Claude Code) A `UserPromptSubmit` hook arms the session (`~/.lens/sessions/<id>/armed.txt`) when the prompt affirmatively invokes the lens; the Stop gate then requires a `lens_run` regardless of writes, and disarms on satisfaction. Detector rejects negations/hedges and ignores lens phrasing quoted inside injected/quoted wrappers (transcript fences, `<task-notification>`) or lens *tooling* (`lens doctor`/`lens close`). Because the arm is a prompt-text heuristic, enforcement is **warn-first** (first unsatisfied stop warns, `skip_reason=arm_warned`; a later one blocks) and **self-clearing** — a 3-block circuit breaker (`arm_abandoned`) and a 2 h TTL (`arm_expired`) — so a false/abandoned arm cannot wedge the session. A watched-write block does not consume the arm's warn/breaker budget. Cursor arming (`beforeSubmitPrompt`) is deferred (I-9) | US-3 arming box |
| F3.2 | Block message tells the worker exactly what to do (invoke `lens` agent, deliverable key convention) | message contains the §7.3 invocation template |
| F3.3 | `enforce=false` in config disables blocking but the hook still emits a one-line warning | toggling requires no reinstall |
| F3.4 | Every firing appends a `hook_check` record (§7.6) to the run log, including its own `duration_ms` | §1 criterion 3, NFR-3, and NFR-4 are computable from the log alone |

### F4 — Run log & close command

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F4.1 | Log lives at config `log_path`; append-only; created on first write | 100% of pilot writes are single-line appends (NFR-2) |
| F4.2 | `/lens-close` command appends a §7.2 record; refuses a deliverable key with no `lens_run` | US-5 acceptance |
| F4.3 | `/lens-doctor` validates: config resolvable, every known named lens parses per §7.5, log writable, host hooks present, Cursor sandbox roots for lens directories | exits non-zero with a named failing check |

### F5 — Cursor support

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F5.1 | Repo ships the Cursor lens subagent (`agents/cursor/lens.md`, `readonly: true`) via `.cursor-plugin/` — same semantics as F2.1 in Cursor's subagent format | US-6 acceptance; diff vs the Claude runner shows only host-format changes |
| F5.2 | Cursor `stop` hook mirrors F3 semantics via `followup_message` (bounded continuation, `loop_limit` default 5 — accepted per the feasibility evaluation); `afterFileEdit` records writes for detection; appends `hook_check` with `host` | US-6 acceptance |
| F5.3 | Cursor install is the `.cursor-plugin/` marketplace import (Team Marketplace / local); `/lens-doctor` merges lens directories into `~/.cursor/sandbox.json` `additionalReadonlyPaths`; both hosts resolve the same `~/.lens/config.json` (§7.4) | `/lens-doctor` green covers both hosts |
| F5.4 | Hook check logic is one shared Python implementation (`lens_lib.check`) with two host entry points | grep-verifiable: no duplicated check logic between hosts |

## 5. Pricing model

Not applicable — the plugin hosts, proxies, and bills nothing; it is a free personal tool distributed via a private repo.

## 6. Design principles

Omitted — every load-bearing principle is a Req (single source of truth = F2.2; enforcement over convention = F3; no data no experiment = F4).

## 7. Cross-cutting contracts

All schemas are JSON Schema Draft 2020-12. Contracts directory in the plugin repo: `contracts/`.

### 7.1 `lens_run` record

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "lens_run.schema.json",
  "type": "object",
  "required": ["ts", "event", "lens", "deliverable", "rounds", "verdict", "findings", "escalations"],
  "properties": {
    "ts": { "type": "string", "format": "date-time" },
    "event": { "const": "lens_run" },
    "lens": { "type": "string", "description": "configured lens name used for this run" },
    "deliverable": { "type": "string", "minLength": 1 },
    "rounds": { "type": "integer", "minimum": 1 },
    "verdict": { "enum": ["pass", "escalated"] },
    "host": { "enum": ["claude-code", "cursor"], "description": "absent in records written before Cursor support = claude-code" },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["round", "check", "target", "severity", "reaction"],
        "properties": {
          "round": { "type": "integer", "minimum": 1 },
          "check": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$" },
          "target": { "type": "string" },
          "severity": { "enum": ["FIX", "ESCALATE"] },
          "reaction": { "enum": ["fixed", "fixed-class", "disputed", "escalated"] },
          "note": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "escalations": { "type": "array", "items": { "type": "string" } }
  },
  "additionalProperties": false
}
```

### 7.2 `human_review` record

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "human_review.schema.json",
  "type": "object",
  "required": ["ts", "event", "deliverable", "corrections"],
  "properties": {
    "ts": { "type": "string", "format": "date-time" },
    "event": { "const": "human_review" },
    "deliverable": { "type": "string", "minLength": 1 },
    "corrections": { "type": "integer", "minimum": 0 },
    "misses": { "type": "array", "items": { "$ref": "#/$defs/tagged_note" } },
    "noise": { "type": "array", "items": { "$ref": "#/$defs/tagged_note" } }
  },
  "$defs": {
    "tagged_note": {
      "type": "object",
      "required": ["check", "note"],
      "properties": {
        "check": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$" },
        "note": { "type": "string" }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 7.3 Runner invocation (worker → runner, prompt-mediated; typed fields)

Input:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "runner_input.schema.json",
  "type": "object",
  "required": ["round", "deliverable"],
  "properties": {
    "lens": { "type": "string", "description": "configured lens name; defaults to config default_lens" },
    "round": { "type": "integer", "minimum": 1 },
    "deliverable": { "type": "string", "description": "stable key; identical across rounds" },
    "files": { "type": "array", "items": { "type": "string" } },
    "sources": { "type": "array", "items": { "type": "string" } },
    "prior_findings": {
      "type": "array",
      "items": { "$ref": "lens_run.schema.json#/properties/findings/items" }
    }
  },
  "additionalProperties": false
}
```

Output: verdict `PASS | FIX | ESCALATE`; findings and escalations exactly as they will be logged (§7.1 shapes). The reply also restates, on FIX, the loop instruction (fix the whole class, re-sweep, return with reactions).

### 7.4 `~/.lens/config.json`

Name resolution order for a lens name: (1) `lenses[name]` if present; (2) else `<lenses_dir>/<name>.md` if that file exists; (3) else unknown. `default_lens` is used when the worker omits `lens`. Env overrides: `LENS_LOG_PATH`, `LENS_DEFAULT`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "config.schema.json",
  "type": "object",
  "required": ["log_path", "default_lens"],
  "properties": {
    "lenses": {
      "type": "object",
      "description": "map of kebab-case lens name → absolute path to a .md lens file",
      "additionalProperties": { "type": "string" }
    },
    "lenses_dir": {
      "type": "string",
      "description": "optional directory; names not in `lenses` resolve to <lenses_dir>/<name>.md"
    },
    "default_lens": {
      "type": "string",
      "description": "lens name used when the worker omits lens"
    },
    "log_path": {
      "type": "string",
      "description": "absolute path to the append-only lens_runs.jsonl file"
    },
    "enforce": { "type": "boolean", "default": true },
    "watch_globs": {
      "type": "array",
      "items": { "type": "string" },
      "default": ["**/*.md", "**/*.html", "**/*.pptx"],
      "description": "fnmatch patterns tested against each written file's path relative to the session working directory AND its absolute path; paths under ~/.claude/ and the system temp directory never match"
    }
  },
  "additionalProperties": false
}
```

### 7.5 Lens file input shape (opinionated — the runner never infers)

A lens is a markdown file resolved from a configured name (`lenses` map or `lenses_dir/<name>.md`). Required, in this order: YAML frontmatter; `## Core principle`; `## When To Run This`; `## Process` — free prose or numbered prelude steps allowed, then one or more bold `**<Check block>?**` question blocks of bullet checks, optionally a closing `Finish:` line; `## Failure-Mode Guards`. Additional sections (an H1 title, `## Stable priors`, …) are allowed and ignored by validation. Every slug maps to exactly one Process bullet, but not every bullet carries a slug; a finding that fires on an uncovered check mints one per F2.3. The canonical slug list lives in the runner agent file (F2.3). A file missing `## Process` or containing no check block fails `/lens-doctor` (F4.3) and the runner declines it at invocation. Shape verified against any file matching this structure (see `tests/fixtures/sample_lens.md`).

### 7.6 `hook_check` record (appended by the Stop hook, F3.4)

Canonical schema: `contracts/hook_check.schema.json`. Notable fields beyond the required core: `wrote_watched` (any watched activity in the session — M3 join key), `watched_writes` (unsatisfied remainder after Cursor `after_ts` filter), `armed` (session was armed by an explicit lens invocation — requires a `lens_run` regardless of writes, warn-first then blocks, F3.5), `session_ids`, `enforce`, `gate` (`none`|`time`|`session`), `excluded_writes`, `skip_reason` (adds `arm_warned` / `arm_abandoned` / `arm_expired` for the arming lifecycle).

Shares the run-log file; analyses select by `event`, so the newest-record-per-deliverable rule for `lens_run` is unaffected. M3 uses `enforce=true ∧ wrote_watched=true → blocked=false`, not `watched_writes ∧ lens_run_found` (Cursor prune makes the latter structurally empty on healthy loops).

## 8. Technical constraints & preferences

- Hosts in the plugin release: Claude Code (`.claude-plugin/` marketplace) and Cursor (`.cursor-plugin/` marketplace — Team Marketplace / local import; desktop IDE). Codex: Appendix B only.
- Python 3 stdlib only for hooks/commands (F1.3); no network calls anywhere in the plugin release — lens bodies are local files; sync is the owner's choice (git, sync disk, etc.).
- No Lexicon/`vault`/`area` concepts in config or contracts — only named lenses, absolute file paths, and `log_path`.
- macOS is the only supported OS in the plugin release.
- Private GitHub repo preferred; install auth = existing git credentials.
- Codegen consumption: this document **is** `docs/PRD.md`; repo `CLAUDE.md` points agents at it and at `contracts/`; the historical v0 agent (`~/.claude/agents/lens.md`) was the reference for the first port (F2.1) — the in-repo runners are now canonical.

## 9. Non-functional requirements

| NFR | Target | Measurement |
| --- | --- | --- |
| NFR-1 record validity | 100% of log lines validate against their event's schema (§7.1/§7.2/§7.6) | schema validation of the full log file at M3 |
| NFR-2 log integrity | 100% of writes are single complete JSONL lines | `jq -e` parse of every line at M3, full file |
| NFR-3 enforcement false blocks | < 5% of `blocked=true` `hook_check` records judged false at pilot review | all `blocked=true` records in the seven days following hook activation (M1 → M3), min 20 total firings |
| NFR-4 hook overhead | p95 `duration_ms` ≤ 500 | `duration_ms` of all `hook_check` records in the same window as NFR-3, min 50 firings |

## 10. Out of scope (canonical)

- Agent Deck lens card + MCP fetch (gated on `human_review` pilot data — see Decision)
- Codex host (feasible per the evaluation above; port sketch in Appendix B)
- Cursor CLI surface (hook delivery documented-limited and reported unreliable — feasibility section; desktop IDE only in this release)
- Team/shared lenses; any multi-user concern
- Correction-capture automation (proposing lens criteria from live corrections)
- agent-dealer gate integration; standalone product
- Windows/Linux support
- Runner latency telemetry (per-round timing is not recorded in the plugin release; only hook overhead is measured)

## 11. Milestones

Dependency order, no calendar estimates — the build is expected to land in about a day of agent implementation. Only the measurement window carries real time, and it is anchored to an event, not a date.

| Milestone | Exit criteria |
| --- | --- |
| M1 — build (laptop 1) | Repo + dual marketplace skeleton; named-lens config + runners (F1–F2); `/lens-doctor` (F4.3); Stop/`stop` hooks (F3/F5); Cursor plugin path (F5) — US-1, US-2, US-2b, US-6, and US-3's functional boxes (all but the NFR-3 rate) pass |
| M2 — deploy (laptop 2) | `/lens-close` (F4.2); install both hosts on laptop 2; US-4 + US-5 acceptance pass |
| M3 — pilot readout | Seven days of real usage after M1 hook activation: §1 success criteria and all §9 NFRs evaluated over their stated windows |

Owner for all milestones: lens owner (side project).

## 12. Open decisions

| Question | Status / default | Owner |
| --- | --- | --- |
| Multiple lenses on one machine? | **Decided** — named `lenses` map and/or `lenses_dir`; one shared `log_path`; invoke by name (F1.2, F1.4, US-2b) | lens owner |
| Does the hook watch code files too? | plugin release: no — `watch_globs` defaults target documents; code review stays with existing tools | lens owner |
| Cursor install mechanism? | **Decided** — `.cursor-plugin/` marketplace (Team Marketplace / local import); doctor merges sandbox readonly roots (F5.3). Not a hand-merge into `~/.cursor/agents` | lens owner |

(Session identification and the slug vocabulary's home were open in draft; both are now specified — F3.1 and F2.3.)

## 13. How to use this document

- **Human (lens owner):** the product half (above the divider) carries the Decision and open questions; in the PRD, review §1 success criteria and §12 — everything else is implementation.
- **AI codegen:** load `docs/PRD.md`; implement one Req at a time in F-number order; check acceptance boxes as you verify; keep `contracts/` identical to §7; when a choice isn't specified, pick the minimum that satisfies the acceptance box; §10 is a hard stop-list.
- **Reference implementation:** in-repo `agents/lens.md` and `agents/cursor/lens.md` plus `python/lens_lib/` — do not reinvent contracts.

## Appendix A — source notes

| Source | Captured as |
| --- | --- |
| [[Sources/Ideas/personal/2026-07-30 Buddy-agent experiment — lens runner brief]] | §7.1/§7.2 record shapes' origin, known v0 gap, dedupe rule |
| v0 runner (`~/.claude/agents/lens.md`) + run log (owner filepath) | F2 semantics, §7.1 field shapes as logged in practice |
| lens markdown file | lens input shape (§7.5), slug vocabulary |
| AI-Codegen PRD Scaffold (`pb_prd_scaffold`, product deck) | PRD section structure, contracts/NFR/open-decision conventions |
| Cursor & Codex feasibility section (above, with doc URLs) | F5 mechanisms; Appendix B port sketch |

## Appendix B — Codex port sketch (out of scope for this release)

Feasibility: strong on CLI/desktop, evaluated 2026-08-01 (section above, with citations). A future port needs, mirroring F2/F3/F4: a reviewer subagent at `~/.codex/agents/lens.toml` (`sandbox_mode = "read-only"`, `developer_instructions` resolving named lenses via the same `~/.lens/config.json`); a `Stop` hook returning `{"decision": "block"}` running the same shared check logic (F5.4's third entry point); `writable_roots` (or hook-side append) for `log_path` with `host: "codex"` added to the §7.1/§7.6 enums. Blocked surface: the IDE extension (hooks undocumented). Not built now because the pilot measures two hosts first; the shared-logic design (F5.4) keeps the port to roughly one TOML file plus one hooks entry.
