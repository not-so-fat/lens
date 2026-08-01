# Lens

Personal review standards for AI agents. One private repo installs on any Mac as a **Claude Code plugin** and a **Cursor plugin**, sharing config, contracts, and the vault run log.

Canonical product + implementation spec: [`docs/PRD.md`](docs/PRD.md).

## Prerequisites

- macOS
- Python 3 (stdlib only — no pip install)
- A vault with `Direction/Lenses/` and writable `Metadata/usage/` (Lexicon or equivalent)

## Configure (both hosts)

```bash
mkdir -p ~/.lens
cat > ~/.lens/config.json <<'EOF'
{
  "vault_root": "/absolute/path/to/your/vault",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}
EOF
```

Override for one session: `export LENS_VAULT_ROOT=/absolute/path/to/your/vault`.

## Install — Claude Code

```bash
claude plugin marketplace add not-so-fat/lens   # or local path / git URL
claude plugin install lens@lens-plugins
```

New session should list the `lens` agent. Run `/lens-doctor`.

## Install — Cursor (desktop IDE)

Private repo: add this GitHub repo as a **Team Marketplace** (Dashboard → Settings → Plugins), or import/load the local clone as a plugin. Public Cursor Marketplace submission is out of scope.

Then run `/lens-doctor` (or `python3 python/ -m` via the doctor command). Doctor merges `vault_root` into `~/.cursor/sandbox.json` `additionalReadonlyPaths` so the runner can read lenses.

Cursor CLI hook delivery is excluded (§10 of the PRD).

## Usage

Worker agents invoke the `lens` subagent with:

- `lens` (default `yusuke`), `area` (default `kite`), `round`, `deliverable` (stable key)
- `files` / `sources`, and on later rounds `prior_findings` + reactions

On a terminal round the runner appends one `lens_run` line to `<vault>/Metadata/usage/lens_runs.jsonl`.

After your human review:

```text
/lens-close "my-deliverable-key" corrections=0
```

## Doctor

```text
/lens-doctor
```

Checks: config source, vault reachable, sample lens shape, log writable, host hooks present, Cursor sandbox path.
