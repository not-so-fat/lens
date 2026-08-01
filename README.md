# Lens

Personal review standards for AI agents. One private repo installs on any Mac as a **Claude Code plugin** and a **Cursor plugin**, sharing config, contracts, and a JSONL run log.

Canonical product + implementation spec: [`docs/PRD.md`](docs/PRD.md).

## Prerequisites

- macOS
- Python 3 (stdlib only — no pip install)
- A lens markdown file (any path) and a writable path for the run log

## Configure (both hosts)

```bash
mkdir -p ~/.lens
cat > ~/.lens/config.json <<'EOF'
{
  "lens_path": "/absolute/path/to/your-lens.md",
  "log_path": "/absolute/path/to/lens_runs.jsonl",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}
EOF
```

Session overrides: `export LENS_PATH=...` and `export LENS_LOG_PATH=...` (both required when using env).

## Install — Claude Code

```bash
claude plugin marketplace add not-so-fat/lens   # or local path / git URL
claude plugin install lens@lens-plugins
```

New session should list the `lens` agent. Run `/lens-doctor`.

## Install — Cursor (desktop IDE)

Private repo: add this GitHub repo as a **Team Marketplace** (Dashboard → Settings → Plugins), or import/load the local clone as a plugin. Public Cursor Marketplace submission is out of scope.

Then run `/lens-doctor`. Doctor merges the lens file's parent directory into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.

Cursor CLI hook delivery is excluded (§10 of the PRD).

## Usage

Worker agents invoke the `lens` subagent with:

- `round`, `deliverable` (stable key)
- `files` / `sources`, optional `lens_path` override
- on later rounds: `prior_findings` + reactions

On a terminal round the runner appends one `lens_run` line to `log_path`.

After your human review:

```text
/lens-close "my-deliverable-key" corrections=0
```

## Doctor

```text
/lens-doctor
```

Or write config in one step:

```bash
PYTHONPATH=python python3 -m lens_lib doctor \
  --write-lens /absolute/path/to/your-lens.md \
  --write-log /absolute/path/to/lens_runs.jsonl
```

Checks: config, lens file shape, log writable, host hooks, Cursor sandbox path.
