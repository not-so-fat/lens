# Release process

Lens ships as a **GitHub repo marketplace** (Claude Code + Cursor). There is no separate package registry. A release is: merge to `main` → bump version fields → git tag → GitHub Release → reinstall/update on each laptop.

## Version fields (keep in sync)

Bump these five together (semver, currently `0.2.4`):

| File | Field |
| --- | --- |
| `.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` | plugin entry `version` |
| `.cursor-plugin/plugin.json` | `version` |
| `.cursor-plugin/marketplace.json` | `metadata.version` + plugin entry `version` |
| `.codex-plugin/plugin.json` | `version` |

Git tag form: `vMAJOR.MINOR.PATCH` (e.g. `v0.1.1`).

## Pre-release checklist

1. **Tests**
   ```bash
   PYTHONPATH=python python3 -m unittest discover -s tests -v
   ```
2. **Runner consistency (#9)** — `tests/test_runner_consistency.py` must pass. Claude (`agents/lens.md`) and Cursor (`agents/cursor/lens.md`) keep host-specific Logging / frontmatter, but spans wrapped in `<!-- SHARED:name START/END -->` must be byte-identical (`role`, `paths`, `procedure`, `reply`). Edit shared prose inside those markers on **both** files the same way (or copy one side to the other). Highest-risk drift: the check-slug vocabulary inside `SHARED:procedure`.
3. **Doctor smoke** (optional but recommended on a real machine): `/lens-doctor` green after install.
4. **PR merged** to `main` (default branch). Do not tag from a feature branch tip unless that tip is what `main` is.

## Cut a release

From a clean checkout of `main`:

```bash
# 1. Confirm tip
git checkout main
git pull origin main

# 2. Bump the five version fields if this cut is a new semver
#    (skip if already bumped in the merge)

# 3. Tag + push
git tag -a v0.1.1 -m "lens v0.1.1"
git push origin v0.1.1

# 4. GitHub Release (notes for humans / changelog)
gh release create v0.1.1 --title "v0.1.1" --notes-file - <<'EOF'
## Lens v0.1.1

First dual-host plugin release (Claude Code + Cursor desktop).

### Install
- Claude: `claude plugin marketplace add not-so-fat/lens` then `claude plugin install lens@lens-plugins`
- Cursor: Import marketplace `https://github.com/not-so-fat/lens` (pin `v0.1.1`), install `lens`, reload, `/lens-doctor`

Pin installs to tag `v0.1.1` when you need a frozen revision. See README “Install” for the marketplace flow (both hosts); the git-clone/local-dir method is under “Local development”.
EOF
```

## After release — each laptop

1. Refresh marketplace / reinstall plugin (or re-import the tagged revision).
2. Run `/lens-doctor`.
3. Optional Cursor smoke: README “Manual Cursor smoke”.

Hosts often pin a marketplace commit; a tag/Release makes the intended revision obvious when something drifts.

## What not to do

- Do not ship with failing `test_runner_consistency` (shared slug / procedure drift).
- Do not bump only one host’s `plugin.json`.
- Do not treat GitHub Release assets as required — the install source is the git tree at the tag.
