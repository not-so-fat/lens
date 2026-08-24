# Lens efficiency — class sweep, fix-regression, cite-stability

**Date:** 2026-08-17  
**Status:** implemented (PR #8)  
**Branch:** `feat/lens-efficiency-class-sweep`  
**Evidence:** 224 runs / 127 deliverables since 2026-08-01 (`~/.lens/lens_runs.jsonl`). Tail waste (≥5 rounds) clusters in `sibling-inconsistency` and `source-grounded` (pilot log analysis, Aug 2026). **Hypothesis** this spec targets: instance fixes leave sibling/cite drift that shows up one round late.

## Goal

Cut late-round churn without changing round semantics or the healthy median path (≤2 rounds for most deliverables). Make class-wide fix + class verification a rule, not an emergent `fixed-class` habit.

## Non-goals

- No change to round numbering, terminal-round logging, or Stop-hook gate semantics.
- No new check slug (e.g. no `fix-regression`).
- No enumerated `class` vocabulary in schema (flexibility for one-offs and new patterns; minting reuse is a runner rule, not an enum).
- No change to reaction enum (`fixed` | `fixed-class` | `disputed` | `escalated`).

## Decisions (locked)

| Topic | Choice |
| --- | --- |
| Class field | Optional `class` on findings in the schema; runner **must** set it for repeatable patterns (one-offs omit it). Not schema-required on every finding. Same kebab pattern as `check`. |
| Fix-regression | Procedure step on rounds ≥ 2 only (no new slug) |
| Cite-stability | Round-1 FIX under existing `source-grounded` when fragile line cites appear; worker remediates by symbol/anchor cites **or** one end-of-loop re-derive |
| Hosts | Claude + Cursor + Codex |

## Design

### 1. Optional `class` on findings (contract)

Add optional string property `class` to finding items in:

- `contracts/lens_run.schema.json`
- PRD §7.1 (must match contracts)
- Runner logging examples in `agents/lens.md`, `agents/cursor/lens.md`, `agents/codex/lens.toml`

Rules:

- One-off findings omit `class`.
- When the finding is an instance of a repeatable pattern, `class` is **required by runner procedure** (not by JSON Schema conditionals).
- `class` uses the same schema pattern as `check`: `^[a-z0-9]+(-[a-z0-9]+)*$`. Prelude step A keys on string equality, so case/spacing variants would silently break class verify.
- **Minting (F2.3-style):** before minting a new `class` label, reuse one already present on prior findings for this deliverable, or grep the run log for an existing label covering the same class. Do not invent near-duplicates (`stale-cite` vs `fragile-line-cites` for the same cite-drift class).
- Reserved starter label: `fragile-line-cites` (§4) — use that exact string for fragile `file:line` cite findings.
- Examples of patterns that require `class`: stale cite, mirrored file, cross-reference, renumbered pointer — and any similar “fix one instance, siblings drift” shape.
- Schema remains `additionalProperties: false` with `class` listed explicitly.
- `runner_input.schema.json` inherits via `$ref` to finding items — no separate edit unless the ref breaks.

### 2. Class-level finding contract (runner procedure)

In SHARED `procedure` / `reply` (and Codex equivalent):

**When raising a repeatable-class finding:**

1. Set `class` to a stable label for that class (reuse-before-mint per §1).
2. Name the class in the reply note (not only the instance `target`).
3. Require a **class-wide sweep** in the FIX reminder (all comparable elements, not just the flagged instance).
4. Prefer the worker reaction `fixed-class` when they report sweeping the class.

This turns today’s reply line (“fix the whole class…”) into an explicit raise rule. Round ≥2 verification of `class` is step A in §3.

### 3. Rounds ≥ 2 prelude (ordered, before Process)

On rounds ≥ 2, after reading prior findings and the worker’s reactions, run these steps **in order**, then walk lens Process for new content:

**A. Class verify** — For each prior finding that has `class`, re-sweep that class scope (not only the prior `target`), even when the reaction is `fixed` or `fixed-class`. **Skip when reaction is `disputed` or `escalated`** — those paths leave the class with the human/worker dispute, not a claimed sweep; re-sweeping would re-litigate an open dispute. New drift in the same class → same `check` + same `class` (new `target` / note as needed), not a fresh unlabeled instance.

**B. Fix-regression** — Diff / re-read siblings and mirrors of sections the worker touched while fixing. If drift appears, raise normal findings (`sibling-inconsistency` / `source-grounded` as appropriate), with `class` when the issue is repeatable. No dedicated check slug.

**C. Process walk** — Execute the lens Process as today.

A and B may surface overlapping drift; prefer one finding per class (reuse `class`) rather than duplicate unlabeled instances.

### 4. Cite-stability (round 1)

When the deliverable cites moving code via fragile locators (`file:line` and equivalents) into same-day-edited or actively changing sources:

- Raise **one** FIX under an existing check (prefer `source-grounded`).
- Set `class` to the reserved label `fragile-line-cites` (do not mint a synonym).
- Note must offer either remediation: symbol/anchor cites, **or** a single end-of-loop re-derive pass.
- Same severity vocabulary as any other FIX; not a second PASS gate beyond clearing that finding.

### 5. Surfaces and consistency

| File | Change |
| --- | --- |
| `contracts/lens_run.schema.json` | optional `class` with same pattern as `check` |
| `docs/PRD.md` | §7.1 + new **F2.5** (class field + class-sweep / fix-regression / cite-stability runner rules) with acceptance checkboxes |
| `agents/lens.md` | SHARED procedure + reply; logging example |
| `agents/cursor/lens.md` | same SHARED spans (byte-identical) |
| `agents/codex/lens.toml` | equivalent procedure/reply/logging |
| `tests/test_runner_consistency.py` | must still pass for Claude/Cursor SHARED spans |
| `tests/` (schema fixture) | validate finding items: with `class`, without `class`, reject unknown key / bad `class` pattern |

### 6. Acceptance (product)

- Finding schema accepts records with and without `class`; rejects unknown finding keys and non-kebab `class` values — covered by the schema fixture test in §5.
- Runners instruct: repeatable → set `class` (reuse-before-mint) + class-wide sweep; round ≥2 → ordered prelude A (class verify) → B (fix-regression) → C (Process); round 1 → cite-stability FIX (`fragile-line-cites`) when fragile line cites appear.
- Round semantics unchanged: terminal round still PASS or all-ESCALATE; log only on terminal (existing F2.4).
- Claude/Cursor SHARED spans remain identical; Codex mirrors the same rules.

## Out of scope for this change

- Analytics jobs or log backfills.
- Enumerating allowed `class` values in schema (reserved labels like `fragile-line-cites` live in runner prose, not an enum).
- Changing `severity` or inventing a second severity axis.
- Reinterpreting cumulative `rounds` across sessions (log note only if mentioned in PRD/docs: multi-session re-review is intended gate behavior).

## Success signal (post-ship, observational)

On a later slice of `lens_runs.jsonl`: fewer deliverables with ≥5 rounds driven by repeated `sibling-inconsistency` / `source-grounded` without `class` / `fixed-class`; organic “class swept” behavior becomes the default path for those checks.
