---
area: personal
created: 2026-07-31
updated: 2026-08-01
tags:
  - idea
  - prd
topics:
  - side_projects
  - agent_deck
status: refining
triaged:
triage_note:
promotes-to:
related:
  - "`Direction/Lenses/<lens>.md`"
  - "[[Sources/Ideas/personal/2026-07-30 Buddy-agent experiment — lens runner brief]]"
  - "[[Sources/Ideas/personal/2026-07-30 Task-Specific Lenses — Product Insight from the Half-Year Review Session]]"
  - "[[Sources/Ideas/personal/2026-07-31 Taste profile — extracted from session history]]"
  - "[[Sources/Ideas/personal/2026-07-30 Buddy Agent — Review Loop Across Hosts]]"
source: "Claude Code sessions 2026-07-30/31 — buddy-agent experiment, run-log review, taste extraction; plugin PRD per AI-Codegen PRD Scaffold (pb_prd_scaffold)"
---

# Lens — personal review standards for AI agents (product idea + plugin PRD)

> **Canonical home:** this file lives in the `lens` plugin repo (`docs/PRD.md`). Implementation note (2026-08-01): Cursor support uses the native `.cursor-plugin/` marketplace (Team Marketplace / local import), not a hand-merge into `~/.cursor/`; F5.3’s install-script wording is superseded. Doctor still merges `vault_root` into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.

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

- 16 real deliverables ran produce → lens review → fix loops: 109 findings, 105 resolved agent-to-agent (37 as whole-class fixes), and the human saw only 2 escalations + 2 disputes. 15 of 16 loops closed in 2–3 rounds. (Run log: `Metadata/usage/lens_runs.jsonl`, records through 2026-07-31T20:02Z, newest record per deliverable.)
- The two verification directions have different economics — truth checks run autonomously and catch what humans can't audit at scale; taste converges only through corrections promoted into the lens ([[Sources/Ideas/personal/2026-07-30 Task-Specific Lenses — Product Insight from the Half-Year Review Session]]).
- Bootstrapping is cheap: mining 23 sessions of existing history produced 6 new lens criteria in one pass ([[Sources/Ideas/personal/2026-07-31 Taste profile — extracted from session history]]). Onboarding = mine the user's own history, not ask them to write rules from scratch.

## Product shape — each piece maps to an observed need

| Piece | Observed need it answers |
| --- | --- |
| **Lens file** — versioned review protocol, human-owned, per person / task family | corrections repeated 5+ times because they had nowhere to live |
| **Runner** — reviewer agent that executes the lens in a loop until pass or escalate | 105 of 109 findings resolved without the human |
| **Correction capture** — live corrections and history mining become proposed criteria | taste is not discoverable by the reviewer; it converges via feedback |
| **Run log + analytics** — every run recorded, joined with the human's final review | retrospective and log disagreed (15/13 recalled vs 14/11 logged at the time); only the log made the discrepancy detectable and resolvable |
| **Multi-host enforcement** — plugin/hooks per host, lens fetched from one source | v0's review loop is a remembered convention — recorded as the known gap in the experiment brief |

## Deployment path (personal need first)

1. **Now:** file-based v0 — lens in the vault, runner as a local agent file, one laptop.
2. **Next: one private repo — Claude Code plugin + Cursor support** — any laptop, one install command per host; lens root configurable. Spec: the plugin PRD below.
3. **Then:** lens as an Agent Deck card — per-business lens switching via deck binding; Codex reached through the existing deck MCP + stub machinery (feasibility evaluated below).

## Positioning

Agent Deck is context switching; a lens is judgment that must travel with that context — a natural deck card type, not a third product. agent-dealer automates the same gate for queued/unattended work. A standalone product only becomes worth considering if deck distribution fails (hosts without Deck, non-agent surfaces).

## Cursor & Codex feasibility (evaluated 2026-08-01)

| Capability the loop needs | Cursor | Codex |
| --- | --- | --- |
| Reviewer with fresh context | YES — subagents: `.cursor/agents/` (project) or `~/.cursor/agents/` (user), `readonly: true`, own context window ([docs](https://cursor.com/docs/subagents)) | YES on CLI/desktop — subagents: `~/.codex/agents/*.toml`, read-only sandbox, fresh session ([docs](https://learn.chatgpt.com/docs/agent-configuration/subagents)) |
| Lens from vault path or MCP | YES, one config step — `sandbox.json` `additionalReadonlyPaths`, or MCP ([sandbox](https://cursor.com/docs/reference/sandbox), [MCP](https://cursor.com/docs/mcp)) | YES — file reads unrestricted by sandbox ([config](https://learn.chatgpt.com/docs/config-file/config-advanced)); MCP config shared across CLI/desktop/IDE ([MCP](https://learn.chatgpt.com/docs/extend/mcp)) |
| Blocking enforcement at turn end | YES on desktop IDE — `stop` hook returns `followup_message`, bounded forced continuation (`loop_limit`, default 5); hooks GA, config at `~/.cursor/hooks.json` (user) or project ([docs](https://cursor.com/docs/hooks)) | YES on CLI/desktop — `Stop` hook `{"decision": "block"}` re-prompts until satisfied ([docs](https://learn.chatgpt.com/docs/hooks)) |
| JSONL append to the vault log | YES — hook scripts run outside the sandbox ([hooks](https://cursor.com/docs/hooks)); agent writes need `additionalReadwritePaths` ([sandbox](https://cursor.com/docs/reference/sandbox)) | YES — `writable_roots` config ([config](https://learn.chatgpt.com/docs/config-file/config-advanced)), or hook-side append ([hooks](https://learn.chatgpt.com/docs/hooks)) |

**Verdict: the loop ports to both hosts with native primitives — feasibility does not depend on the deck.** Remaining gaps: per-surface — Cursor CLI hook delivery is documented-limited ([hooks](https://cursor.com/docs/hooks)) and reported unreliable ([forum report](https://forum.cursor.com/t/cursor-cli-doesnt-send-all-events-defined-in-hooks/148316)); Codex IDE-extension hooks are undocumented ([IDE docs](https://learn.chatgpt.com/docs/codex/ide)) — and one per-host design limit: Cursor's stop gate is bounded continuation (`loop_limit`, default 5), not a hard block. The bounded gate is accepted: 15 of 16 observed loops closed within 3 rounds (Evidence above). The deck card's value is therefore lens distribution/switching, not feasibility.

## Open questions — marked by what each blocks

- **Blocks the deck card** — lens body's home: deck card vs vault file (one source of truth — the no-mirroring rule forces a choice).
- **Resolved for the plugin release by exclusion (§10); reopens at the deck card** — per-surface enforcement gaps: Cursor CLI (hook delivery unreliable) is excluded from the plugin release; the Codex IDE extension (hooks undocumented) remains a deck-card question; the run log's skip rate is the evidence to collect.
- **Shapes the plugin step, worth arguing** — privacy: lenses encode work context; multi-laptop sync must stay private (private repo suffices? deck sync changes the answer).
- **Blocks nothing yet** — team lenses: can a team share standards the way one person does, and who reviews the reviewer?

---

# Plugin PRD — multi-laptop, Claude Code + Cursor

Implementation half (scaffold: pb_prd_scaffold). Everything above is the framing; a coding agent builds from here. Stage naming across this document: **v0 loop** (file-based, running today) → **plugin release** (this PRD: Claude Code plugin + Cursor support) → **deck card** (gated, see Decision).

## 1. Product overview

Scope: package the proven v0 loop (runner agent + lens file + run log) into one private repo that installs on any machine — a Claude Code plugin and Cursor support (subagent + hooks, **desktop IDE**; the CLI surface is excluded, §10) sharing config, contracts, and the run log — so the loop cannot be silently skipped on either host's covered surface. Codex: out of scope, port sketch in Appendix B.

**Success criteria (evaluated at M3 — seven days after hook activation):** plugin installed and passing `/lens-doctor` on 2 laptops; Stop-hook enforcement active on both hosts (Cursor: desktop IDE); ≥ 90% of `hook_check` records with `watched_writes=true` also have `lens_run_found=true` (§7.6, measurement window per §9, min 10 such records, both hosts pooled); ≥ 1 `lens_run` logged from Cursor (`host: "cursor"`); ≥ 5 deliverables carry `human_review` lines.

## 2. Target users & roles

Primary persona: a product lead who produces documents, decks, and specs through coding agents on multiple machines and is the only reviewer of record.

| Role | Goal | Plugin surface |
| --- | --- | --- |
| Lens owner (human) | Standards enforced everywhere; final review only | vault lens file; `/lens-close`; `/lens-doctor` |
| Worker agent | Pass the lens loop before surfacing a deliverable | `lens` subagent invocation contract (§7.3), Claude Code and Cursor |
| Runner (`lens` subagent) | Execute the lens; report FIX/ESCALATE/PASS; log terminal rounds | plugin agent (Claude Code) / `.cursor` subagent (Cursor) + run log (§7.1) |

"I am a product lead / I want my correction standards enforced by agents themselves / I use Lens because corrections that don't compound cost me the ~12-round baseline (Problem, above)." Voice rules: use *lens, runner, worker, finding, run* — never introduce a synonym; "buddy" is allowed as informal alias in prose, never in contracts.

Deferred roles (team members, Codex host): see §10.

## 3. User stories (testable)

**US-1 (plugin). Install on a new laptop.** As a lens owner, I want one-command install so my standards travel.
Acceptance:
- [ ] `claude plugin marketplace add <private-repo>` + `claude plugin install lens` succeeds on a clean machine with repo access
- [ ] a new session lists the `lens` agent
- [ ] `/lens-doctor` exits green after writing `~/.lens/config.json` with a valid `vault_root`

**US-2 (plugin). Run the loop.** As a worker agent, I want to invoke the runner with (lens, area, round, deliverable key, files, prior findings) and get a verdict so simple issues resolve without the human.
Acceptance:
- [ ] runner reply contains verdict `PASS`/`FIX`/`ESCALATE` and findings matching §7.3 output shape
- [ ] every finding cites a `check` slug from the lens vocabulary (F2.3)
- [ ] with `vault_root` unreachable, runner replies `LENS UNAVAILABLE: <path>` and produces no findings

**US-3 (plugin). Enforcement.** As a lens owner, I want a turn that wrote watched files blocked at its Stop-hook firing until a lens run is logged, so the loop cannot be silently skipped.
Acceptance:
- [ ] the Stop-hook firing blocks (exit 2, message names the missing step) when the session has written files matching `watch_globs` (anchoring per §7.4) and the log has no `lens_run` with `ts` ≥ the transcript's first-event time
- [ ] the firing passes when such a `lens_run` exists, when no watched files were written, or when `enforce=false`
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
- [ ] install script registers the Cursor lens subagent (`~/.cursor/agents/`) and merges the `stop` hook into `~/.cursor/hooks.json`; `/lens-doctor` validates both (F5.3)
- [ ] the Cursor subagent reviews per §7.3 and logs per §7.1 with `host: "cursor"`
- [ ] the Cursor `stop` hook returns `followup_message` when watched writes lack a session `lens_run` (bounded by `loop_limit`; F5.2) and appends `hook_check` with `host: "cursor"`
- [ ] the vault is readable from the Cursor sandbox (`sandbox.json` `additionalReadonlyPaths`, written by the install script; F5.3)

Deferred stories (deck card fetch, Codex host, correction-capture automation): see §10.

## 4. Features & requirements

### F1 — Plugin packaging & config

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F1.1 | Private git repo is a Claude Code plugin marketplace: `.claude-plugin/marketplace.json` + plugin `lens` with `agents/`, `hooks/`, `commands/` | US-1 install steps pass on macOS |
| F1.2 | Config resolves env `LENS_VAULT_ROOT` → `~/.lens/config.json` (§7.4) → error with setup instructions | `/lens-doctor` reports the resolved source |
| F1.3 | All hook/command scripts are Python 3 stdlib-only | `grep`-verifiable: no third-party imports |

### F2 — Runner agent

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F2.1 | Plugin ships the runner as `agents/lens.md`, semantics identical to the proven v0 agent, with vault paths replaced by config resolution (F1.2) | US-2 acceptance; diff vs v0 shows only path/config changes |
| F2.2 | Runner reads `Direction/Lenses/<lens>.md` under `vault_root` at invocation time; lens file is the single source of truth (input shape §7.5) | editing the lens changes the next run's checks with no plugin change |
| F2.3 | The canonical per-lens slug list lives in the runner agent file (the vocabulary's home in the plugin release); a new slug is minted only when a finding fires on a check with no slug in the list — whether newly added to the lens or previously uncovered — after grepping the run log for an existing one | no two slugs for one lens question across the pilot log |
| F2.4 | Terminal-round logging per §7.1; non-terminal rounds never log | US-4 acceptance |

### F3 — Enforcement (Stop hook)

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F3.1 | The Stop hook fires at each turn end with the session transcript path; it detects session writes matching `watch_globs` (anchoring per §7.4) and checks the log for a `lens_run` with `ts` ≥ the transcript's first-event time | US-3 acceptance |
| F3.2 | Block message tells the worker exactly what to do (invoke `lens` agent, deliverable key convention) | message contains the §7.3 invocation template |
| F3.3 | `enforce=false` in config disables blocking but the hook still emits a one-line warning | toggling requires no reinstall |
| F3.4 | Every firing appends a `hook_check` record (§7.6) to the run log, including its own `duration_ms` | §1 criterion 3, NFR-3, and NFR-4 are computable from the log alone |

### F4 — Run log & close command

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F4.1 | Log lives at `<vault_root>/Metadata/usage/lens_runs.jsonl`; append-only; created on first write | 100% of pilot writes are single-line appends (NFR-2) |
| F4.2 | `/lens-close` command appends a §7.2 record; refuses a deliverable key with no `lens_run` | US-5 acceptance |
| F4.3 | `/lens-doctor` validates: config resolvable, vault reachable, lens file parses per §7.5, log writable, hook registered | exits non-zero with a named failing check |

### F5 — Cursor support

| Req | Requirement | Acceptance |
| --- | --- | --- |
| F5.1 | Repo ships the Cursor lens subagent (`cursor/agents/lens.md`, `readonly: true`) — same semantics as F2.1 in Cursor's subagent format | US-6 acceptance; diff vs the plugin runner shows only host-format changes |
| F5.2 | Cursor `stop` hook mirrors F3 semantics via `followup_message` (bounded continuation, `loop_limit` default 5 — accepted per the feasibility evaluation); appends `hook_check` with `host` | US-6 acceptance |
| F5.3 | One install script configures Cursor: subagent, `hooks.json` merge, `sandbox.json` vault read path; both hosts resolve the same `~/.lens/config.json` (§7.4) | `/lens-doctor` green covers both hosts |
| F5.4 | Hook check logic is one shared Python implementation with two host entry points | grep-verifiable: no duplicated check logic between hosts |

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
  "required": ["ts", "event", "lens", "area", "deliverable", "rounds", "verdict", "findings", "escalations"],
  "properties": {
    "ts": { "type": "string", "format": "date-time" },
    "event": { "const": "lens_run" },
    "lens": { "type": "string" },
    "area": { "type": "string" },
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
    "lens": { "type": "string", "description": "falls back to config default_lens" },
    "area": { "type": "string", "description": "falls back to config default_area" },
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

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "config.schema.json",
  "type": "object",
  "required": ["vault_root"],
  "properties": {
    "vault_root": { "type": "string", "description": "absolute path to the knowledge base holding Direction/Lenses/ and Metadata/usage/" },
    "default_lens": { "type": "string", "description": "stem of Direction/Lenses/<name>.md when the worker omits lens" },
    "default_area": { "type": "string", "description": "area tag when the worker omits area" },
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

A lens is a markdown file at `<vault_root>/Direction/Lenses/<lens>.md`. Required, in this order: YAML frontmatter; `## Core principle`; `## When To Run This`; `## Process` — free prose or numbered prelude steps allowed, then one or more bold `**<Check block>?**` question blocks of bullet checks, optionally a closing `Finish:` line; `## Failure-Mode Guards`. Additional sections (an H1 title, `## Stable priors`, …) are allowed and ignored by validation. Every slug maps to exactly one Process bullet, but not every bullet carries a slug; a finding that fires on an uncovered check mints one per F2.3. The canonical slug list lives in the runner agent file (F2.3). A file missing `## Process` or containing no check block fails `/lens-doctor` (F4.3) and the runner declines it at invocation. Shape verified against the canonical `Direction/Lenses/<lens>.md`.

### 7.6 `hook_check` record (appended by the Stop hook, F3.4)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "hook_check.schema.json",
  "type": "object",
  "required": ["ts", "event", "session", "watched_writes", "lens_run_found", "blocked", "duration_ms"],
  "properties": {
    "ts": { "type": "string", "format": "date-time" },
    "event": { "const": "hook_check" },
    "session": { "type": "string", "description": "session id from the transcript path" },
    "watched_writes": { "type": "boolean" },
    "lens_run_found": { "type": "boolean" },
    "blocked": { "type": "boolean" },
    "duration_ms": { "type": "number", "minimum": 0 },
    "host": { "enum": ["claude-code", "cursor"], "description": "absent in records written before Cursor support = claude-code" }
  },
  "additionalProperties": false
}
```

Shares the run-log file; analyses select by `event`, so the newest-record-per-deliverable rule for `lens_run` is unaffected.

## 8. Technical constraints & preferences

- Hosts in the plugin release: Claude Code (plugin marketplace format) and Cursor (user-level subagent + `hooks.json`, installed by the F5.3 script). Codex: Appendix B only.
- Python 3 stdlib only for hooks/commands (F1.3); no network calls anywhere in the plugin release — the lens is a local file, sync rides the vault's existing git.
- macOS is the only supported OS in the plugin release.
- Private GitHub repo; install auth = existing git credentials.
- Codegen consumption: this document is copied to `docs/PRD.md` in the plugin repo; repo `CLAUDE.md` points agents at it and at `contracts/`; the existing v0 agent file (`~/.claude/agents/lens.md`) is the canonical reference implementation for F2.1.

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
| M1 — build (laptop 1) | Repo + plugin skeleton; runner ported (F2); config + `/lens-doctor` (F1.2, F4.3); Stop hook active (F3); Cursor support installed (F5) — US-1, US-2, US-6, and US-3's functional boxes (all but the NFR-3 rate) pass |
| M2 — deploy (laptop 2) | `/lens-close` (F4.2); install both hosts on laptop 2; US-4 + US-5 acceptance pass |
| M3 — pilot readout | Seven days of real usage after M1 hook activation: §1 success criteria and all §9 NFRs evaluated over their stated windows |

Owner for all milestones: lens owner (side project).

## 12. Open decisions

| Question | Default if undecided | Owner |
| --- | --- | --- |
| Multiple vaults on one machine? | plugin release: one `vault_root`; per-project override via `LENS_VAULT_ROOT` | lens owner |
| Does the hook watch code files too? | plugin release: no — `watch_globs` defaults target documents; code review stays with existing tools | lens owner |
| Cursor install scope? | user-level (`~/.cursor/`), not per-project — standards are personal, not per-repo | lens owner |

(Session identification and the slug vocabulary's home were open in draft; both are now specified — F3.1 and F2.3.)

## 13. How to use this document

- **Human (lens owner):** the product half (above the divider) carries the Decision and open questions; in the PRD, review §1 success criteria and §12 defaults — everything else is implementation.
- **AI codegen:** load `docs/PRD.md`; implement one Req at a time in F-number order; check acceptance boxes as you verify; use §7 schemas verbatim (copy into `contracts/`); when a choice isn't specified, pick the minimum that satisfies the acceptance box; §10 is a hard stop-list.
- **Reference implementation:** the working v0 runner at `~/.claude/agents/lens.md` — port, don't reinvent (F2.1).

## Appendix A — source notes

| Source | Captured as |
| --- | --- |
| [[Sources/Ideas/personal/2026-07-30 Buddy-agent experiment — lens runner brief]] | §7.1/§7.2 record shapes' origin, known v0 gap, dedupe rule |
| v0 runner (`~/.claude/agents/lens.md`) + run log (`Metadata/usage/lens_runs.jsonl`) | F2 semantics, §7.1 field shapes as logged in practice |
| `Direction/Lenses/<lens>.md` | lens input shape (§7.5), slug vocabulary |
| AI-Codegen PRD Scaffold (`pb_prd_scaffold`, product deck) | PRD section structure, contracts/NFR/open-decision conventions |
| Cursor & Codex feasibility section (above, with doc URLs) | F5 mechanisms; Appendix B port sketch |

## Appendix B — Codex port sketch (out of scope for this release)

Feasibility: strong on CLI/desktop, evaluated 2026-08-01 (section above, with citations). A future port needs, mirroring F2/F3/F4: a reviewer subagent at `~/.codex/agents/lens.toml` (`sandbox_mode = "read-only"`, `developer_instructions` pointing at the lens path); a `Stop` hook returning `{"decision": "block"}` running the same shared check logic (F5.4's third entry point); `writable_roots` (or hook-side append) for the run log with `host: "codex"` added to the §7.1/§7.6 enums; lens read is unrestricted, no config needed. Blocked surface: the IDE extension (hooks undocumented). Not built now because the pilot measures two hosts first; the shared-logic design (F5.4) keeps the port to roughly one TOML file plus one hooks entry.
