# Lens correction capture — implementation plan

**Goal:** Durable correction signals from `/lens-close` and CLI propose/apply rail to promote `human_review.misses` into lens `.md` criteria.

**Architecture:** Append-only `correction_signals.jsonl` + `lens_patches.jsonl` under `~/.lens/`; stdlib Python in `lens_lib`; extend `/lens-close` ingest; CLI subcommand `corrections`; human `apply` writes lens file.

**Tech stack:** Python 3 stdlib, JSON Schema (contracts), existing `lens_parse.py`, pytest.

**PRD:** [PRD_CORRECTION_CAPTURE.md](./PRD_CORRECTION_CAPTURE.md)

## Global constraints

- Stdlib only (F1.3)
- No network calls
- Lens content stays in owner vault paths — not committed to plugin repo
- Human accept via explicit `apply`
- Noise ≠ automatic new check

## File map

| File | Role |
|------|------|
| `contracts/correction_signal.schema.json` | signal row shape |
| `contracts/lens_patch.schema.json` | proposal + ops |
| `python/lens_lib/corrections.py` | append, list, propose, apply |
| `python/lens_lib/corrections.test.py` | SC-1..5 |
| `python/lens_lib/close.py` | hook misses/noise → signals |
| `python/lens_lib/lens_parse.py` | apply ops to Process/guards |
| `commands/lens-close.md` | document signal capture |
| `docs/PRD.md` | §10 amendment when done |

---

## Task 1: Contracts

- [ ] Add `correction_signal.schema.json`
- [ ] Add `lens_patch.schema.json` with ops enum (`add_check`, `amend_check`, `add_guard`)
- [ ] Cross-reference in PRD §7 (new §7.x or appendix pointer)

## Task 2: Signal append from close (TDD)

- [ ] Test: close with misses → N signal lines, valid schema
- [ ] Test: noise → `kind: noise`
- [ ] Test: duplicate close same deliverable → new signals (append-only)
- [ ] Implement in `close.py` after human_review line written
- [ ] Generate stable `cs_*` ids

## Task 3: Corrections CLI — list / show

- [ ] `python -m lens_lib corrections list [--lens NAME] [--status open]`
- [ ] `python -m lens_lib corrections show cs_…` / `lp_…`
- [ ] Read paths from config (`~/.lens/correction_signals.jsonl`, `lens_patches.jsonl`)

## Task 4: Propose (TDD)

- [ ] Test: propose with ≥2 signal_ids links ids, creates `proposed` patch
- [ ] Test: single signal allowed with `--force` only
- [ ] Test: ops reference valid check slugs or declare new slug for add_check
- [ ] `python -m lens_lib corrections propose --lens yusuke --signal-ids cs_a,cs_b --ops-file …`
- [ ] Markdown diff preview to stdout

## Task 5: Apply (TDD)

- [ ] Test: apply updates lens fixture; doctor-valid Process shape preserved
- [ ] Test: marks signals `actioned`, patch `accepted`
- [ ] Test: apply rejected if lens path not in config map
- [ ] `python -m lens_lib corrections apply lp_…`

## Task 6: Lens parse apply helpers

- [ ] `add_check` / `amend_check` / `add_guard` mutators on parsed lens AST or structured sections
- [ ] Reuse slug patterns from runner F2.3

## Task 7: Docs + doctor

- [ ] Update `/lens-close` command doc
- [ ] `/lens-doctor` optional check: correction log file writable
- [ ] Amend PRD §10 out-of-scope list
- [ ] README: one paragraph on correction capture

## Task 8: Verify

- [ ] `pytest python/lens_lib/corrections.test.py`
- [ ] Manual: real deliverable close → list → propose → apply → re-run lens on sample file

---

## Suggested implementation order

1. Task 1–2 (capture — immediate value from existing `/lens-close` habit)
2. Task 6 (parse helpers — needed for apply)
3. Task 4–5 (propose/apply loop)
4. Task 3, 7–8 (UX polish + docs)

## Deferred (v1.1)

- `supersedes` / `amends` for lens patches (parity with deck)
- Import from historical `human_review` lines in `lens_runs.jsonl`
- Deliverable-scoped Stop gate (ISSUES I-7) as separate spec
- Deck card MCP `propose_lens_patch`

## Cross-repo note

When agent-deck implements [PRD_FEEDBACK_CURATION.md](../agent-deck/docs/PRD_FEEDBACK_CURATION.md), reuse the same **curation-first** decision tree wording in lens CLI help for consistency.
