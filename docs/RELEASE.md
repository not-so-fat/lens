# Release process

Lens ships as a **GitHub repo marketplace** (Claude Code + Cursor). There is no separate package registry. A release is: merge to `main` → bump version fields → git tag → GitHub Release → reinstall/update on each laptop.

## Version fields (keep in sync)

Bump these five together (semver, currently `0.2.8`):

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
3. **Manifest ↔ tag check** — `tests/test_release_manifest.py` keeps the five plugin/marketplace `version` fields in sync with `docs/RELEASE.md`. After the version-bump commit is on `main` and tagged, confirm the tag peels to `HEAD`:
   ```bash
   LENS_RELEASE_CHECK=1 PYTHONPATH=python python3 -m unittest tests.test_release_manifest -v
   ```
   Uses annotated tags (`git tag -a`); the check resolves the tagged **commit**, not the tag object.
4. **Doctor smoke** (optional but recommended on a real machine): `/lens-doctor` green after install.
5. **PR merged** to `main` (default branch). Do not tag from a feature branch tip unless that tip is what `main` is.

## Cut a release

From a clean checkout of `main`:

```bash
# 1. Confirm tip
git checkout main
git pull origin main

# 2. Bump the five version fields + commit on main
#    chore(release): bump to vX.Y.Z

git push origin main

# 3. Tag the bump commit (must be HEAD — tag after the bump lands on main)
git tag -a v0.1.1 -m "lens v0.1.1" HEAD
git push origin v0.1.1

# Re-cutting the same version? Delete the stale tag first:
#   git tag -d v0.1.1 && git push origin :refs/tags/v0.1.1

# 3b. Confirm manifest version ↔ tag at HEAD
LENS_RELEASE_CHECK=1 PYTHONPATH=python python3 -m unittest tests.test_release_manifest -v

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

- Do not tag before the version-bump commit is on `main` (tag must peel to `HEAD`).
- Do not reuse a local tag name from an earlier attempt without deleting it first.
- Do not bump only one host’s `plugin.json`.
- Do not treat GitHub Release assets as required — the install source is the git tree at the tag.
