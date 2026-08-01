# Lens

Personal review standards for AI agents — Claude Code plugin + Cursor plugin in one private repo.

## For coding agents

1. Read [`docs/PRD.md`](docs/PRD.md) — product framing + implementation contracts (canonical).
2. Schemas live in [`contracts/`](contracts/) — copy shapes from the PRD; do not invent fields.
3. Python under [`python/`](python/) is **stdlib only** (F1.3). No network calls in the plugin release.
4. Implement / verify by F-number acceptance boxes in the PRD. §10 is a hard stop-list.
5. Reference runner semantics: port of the proven v0 agent (path/config + `host` only).

## Layout

| Path | Role |
| --- | --- |
| `agents/lens.md` | Claude Code runner |
| `agents/cursor/lens.md` | Cursor runner (`readonly`) |
| `hooks/claude-hooks.json` / `hooks/cursor-hooks.json` | Host Stop/stop hooks |
| `python/lens_lib/` | Shared check / config / log / doctor / close |
| `commands/` | `/lens-doctor`, `/lens-close` |

## Voice

Use *lens, runner, worker, finding, run* — never invent synonyms in contracts.
