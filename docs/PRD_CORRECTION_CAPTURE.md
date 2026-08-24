# Lens correction capture — PRD

**Date:** 2026-08-23 · **Status:** Implemented (v1 CLI) · **Repo:** lens  
**Prior art:** [PRD.md](./PRD.md) §10 (correction-capture automation), [human_review schema](../contracts/human_review.schema.json), lens file shape PRD §7.5  
**Implementation plan:** [correction-capture-plan.md](./correction-capture-plan.md)  
**Cross-product:** agent-deck [PRD_FEEDBACK_ACCUMULATION.md](../agent-deck/docs/PRD_FEEDBACK_ACCUMULATION.md) — same *learning-loop shape*, different artifact (taste vs procedure)  
**Inspiration:** [Agentic Transaction](https://arxiv.org/html/2608.13900v1) — failed attempts must not poison durable state; only validated corrections promote into permanent standards.

---

## 1. One job + audience

**One job:** Turn human corrections after lens review into **proposed updates to the lens file** (review criteria), with session-scoped evidence and permanent, versioned promotion — mirroring deck’s `feedback_signals → propose → accept` rail for playbooks.

**Audience:** (1) lens owner closing deliverables (`/lens-close`), (2) worker/runner ecosystem (future automation), (3) future Agent Deck card (distribution only).

**Not this job:** Changing Stop-hook gate semantics, team lenses, backend LLM in lens plugin, auto-editing lens files without human accept, dealer integration.

---

## 2. Product mapping — what is the “playbook”?

| agent-deck | lens |
|------------|------|
| Playbook `.md` (procedure) | **Lens `.md`** (review standards) |
| Gotcha / Checklist bullet | **`## Process` check bullet** (+ `check` slug) |
| `feedback_signals` | **`correction_signals`** (new JSONL — see §5.1) |
| `propose_playbook_patch` | **`propose_lens_patch`** (CLI or MCP later; v1 CLI) |
| Dashboard accept | **Human edits lens file** (v1); optional diff apply command |
| Session scope | `lens_run` + `human_review` per **deliverable** |
| Permanent scope | Named lens file (`~/.lens/config.json` → path), git-versioned by owner |

**Correction sources (priority):**

1. **`human_review.misses`** — runner missed something; primary promotion source (`check` slug + `note`).
2. **`human_review.noise`** — false positive; propose guard/tighten, not new criteria blindly.
3. **Live session corrections** (deferred automation) — user text not captured in `/lens-close`.
4. **History mining** — transcript bootstrap (PRD evidence: 6 criteria / 23 sessions); reuse deck bootstrap patterns later.

**Scope:**

| Layer | Lifetime | Purpose |
|-------|----------|---------|
| Session | One deliverable arc | `lens_run`, findings, FIX rounds, `human_review` |
| Permanent | Cross-session | Lens `.md` criteria; append-only `correction_signals` + patch proposals |

---

## 3. Problem

Lens already enforces **validate-before-surface** (Stop hook, runner loop). Corrections **do not compound** into the lens file automatically:

- PRD §10 defers “correction-capture automation.”
- Owner manually edits lens `.md` after noticing repeated `misses`.
- Same correction given 5+ times across sessions (PRD Problem) — nowhere to live until promoted.

Deck solved the analogous problem with durable signals + curation. Lens needs the same **rail**, not the same **host**.

---

## 4. Reasoning rules (invariants)

1. **Lens file is sole source of truth** — proposals are diffs against configured path; no mirroring into repo plugin.
2. **Human accepts promotion** — v1: human applies diff or runs `lens patch apply` after review; no silent writes.
3. **Noise ≠ miss** — `noise` signals propose tighten/guard; do not auto-add criteria from noise alone.
4. **Disputed findings quarantined** — `reaction: disputed` in `lens_run` does not auto-promote without `human_review` confirmation.
5. **Stdlib-only plugin** — capture CLI in `lens_lib`; no network in plugin release.
6. **Provenance required** — every signal links `deliverable`, `lens` name, optional `lens_run` ts, `check` slug.

---

## 5. Design

### 5.1 `correction_signals` (durable capture)

Append-only store alongside run log (v1: **`~/.lens/correction_signals.jsonl`**, schema-validated).

```json
{
  "ts": "2026-08-23T10:00:00Z",
  "event": "correction_signal",
  "id": "cs_…",
  "lens": "yusuke",
  "deliverable": "kite-meetings-agenda",
  "check": "source-grounded",
  "kind": "miss",
  "note": "Rating must stay human-owned; agent inferred score.",
  "lens_run_ts": "2026-08-23T09:55:00Z",
  "status": "open",
  "linked_patch_id": null
}
```

Statuses: `open` | `actioned` | `discarded` (same lifecycle spirit as deck).

**Ingest v1:**

- `/lens-close` with `misses=[…]` / `noise=[…]` → append one signal per tagged note (`kind`: `miss` | `noise`).
- CLI: `python -m lens_lib corrections import-human-review …` (replay from log).

### 5.2 `lens_patches` (proposals)

File-backed proposals (v1: **`~/.lens/lens_patches.jsonl`**) until deck card owns storage.

```json
{
  "id": "lp_…",
  "status": "proposed",
  "lens": "yusuke",
  "lens_path": "/abs/path/to/yusuke.md",
  "ops": [
    { "op": "add_check", "block": "Source grounded?", "bullet": "- Do not infer ratings; cite source or escalate." },
    { "op": "amend_check", "check": "source-grounded", "bullet": "…" }
  ],
  "signal_ids": ["cs_…"],
  "evidence": { "notes": ["…"] },
  "created_at": "…"
}
```

Ops vocabulary (minimal v1):

| Op | Target |
|----|--------|
| `add_check` | New bold `**Block?**` under `## Process` |
| `amend_check` | Replace bullet under existing `check` slug |
| `add_guard` | Bullet under `## Failure-Mode Guards` |

Slug minting follows existing F2.3 runner rules — proposal must cite existing slug or declare new slug for `add_check`.

### 5.3 Curation-first (same lesson as deck)

| Situation | Action |
|-----------|--------|
| First `miss` on a check theme | log signal only |
| ≥2 open signals same lens + similar `check`/note tokens | `lens corrections propose --signal-ids …` |
| User: “add this to the lens” | immediate propose allowed |
| Wrong proposal | new propose with `supersedes` (deck parity, v1.1) |

### 5.4 Promotion (human accept)

v1 flow:

1. `lens corrections list` — open signals + proposed patches.
2. `lens corrections show lp_…` — render markdown diff preview against lens file.
3. Owner applies manually **or** `lens corrections apply lp_…` (writes lens file, marks signals `actioned`, appends patch status `accepted`).

Optional: git commit reminder in output (owner vault is private).

### 5.5 Gate hardening (optional slice — can ship after capture)

Deliverable-scoped Stop gate (ISSUES I-7): require `lens_run` after last watched write batch for `(session, deliverable)` — prevents early PASS from clearing later edits. Spec separately if bundled; not blocking correction capture.

### 5.6 Future deck card

When deck card lands: move `correction_signals` / `lens_patches` to deck store; MCP `propose_lens_patch` mirrors `propose_playbook_patch`. v1 stays local CLI to unblock pilot without deck dependency.

---

## 6. User stories

### US-1 — Close captures misses

**As** a lens owner  
**I want** `/lens-close` misses to become durable correction signals  
**so that** repeated taste gaps are visible before I edit the lens file.

**Acceptance:** Each `misses[]` entry appends `correction_signal` with `kind: miss`, `status: open`.

### US-2 — Propose criteria from accumulated signals

**As** a lens owner  
**I want** to propose lens criteria from ≥2 related open signals  
**so that** one promotion reflects evidence, not a single offhand note.

**Acceptance:** CLI propose links `signal_ids`; preview shows Process/guard diff.

### US-3 — Apply after review

**As** a lens owner  
**I want** to apply an accepted proposal to my lens file  
**so that** future runs enforce the new standard.

**Acceptance:** `apply` updates lens `.md`, validates via `/lens-doctor`, marks signals `actioned`.

### US-4 — Noise is captured but cautious

**As** a lens owner  
**I want** `noise` logged separately  
**so that** I can tighten guards without treating noise as new criteria by default.

**Acceptance:** `kind: noise` signals; propose defaults to guard/amend, not `add_check`, unless owner overrides.

---

## 7. Out of scope (v1)

- Dashboard UI (deck-hosted later)
- Live mid-session capture without `/lens-close`
- Backend LLM summarization
- Team/shared lenses
- Automatic apply without human `apply`
- Confidence divergence (paper) — no token logprobs in host agents

---

## 8. Success criteria

| # | Criterion |
|---|-----------|
| SC-1 | `/lens-close` with misses appends valid `correction_signal` lines |
| SC-2 | CLI propose from ≥2 signal ids produces previewable `lens_patch` |
| SC-3 | `apply` updates lens file and passes lens-doctor Process validation |
| SC-4 | Noise signals do not auto-`add_check` without explicit op |
| SC-5 | Signals + patches survive restart (durable files) |

---

## 9. PRD §10 amendment (when implemented)

Remove or narrow “Correction-capture automation” from out-of-scope; point to this PRD + CLI commands.

---

## 10. Relationship to agent-deck

```
Lens session          Deck session
     │                      │
     ▼                      ▼
correction_signals    feedback_signals
     │                      │
     ▼                      ▼
lens_patches          playbook_patches
     │                      │
     ▼                      ▼
lens .md              playbook .md
(taste)               (procedure)
```

Same learning-loop **shape**; integrate at deck card phase, not by merging stores prematurely.
