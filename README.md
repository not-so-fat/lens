# Lens

Personal review standards for AI agents. One private repo installs on any Mac as a **Claude Code plugin** and a **Cursor plugin**, sharing config, contracts, and a JSONL run log.

Canonical product + implementation spec: [`docs/PRD.md`](docs/PRD.md).

## Prerequisites

- macOS
- Python 3 (stdlib only — no pip install)
- One or more lens markdown files and a writable path for the run log

## Configure

Register named lenses (once, or gradually):

```bash
mkdir -p ~/.lens
cat > ~/.lens/config.json <<'EOF'
{
  "lenses": {
    "review": "/absolute/path/to/review.md",
    "deck": "/absolute/path/to/deck.md"
  },
  "default_lens": "review",
  "log_path": "/absolute/path/to/lens_runs.jsonl",
  "enforce": true,
  "watch_globs": ["**/*.md", "**/*.html", "**/*.pptx"]
}
EOF
```

Add another later:

```bash
PYTHONPATH=python python3 -m lens_lib lens add story /absolute/path/to/story.md
PYTHONPATH=python python3 -m lens_lib lens list
```

Optional `lenses_dir`: drop `<name>.md` into a folder and invoke with that name (no map entry required).

Env: `LENS_LOG_PATH`, `LENS_DEFAULT` (default lens name).

## Install — Claude Code

```bash
claude plugin marketplace add not-so-fat/lens   # or local path / git URL
claude plugin install lens@lens-plugins
```

New session should list the `lens` agent. Run `/lens-doctor`.

## Install — Cursor (desktop IDE)

Import this repo as a Team Marketplace / local plugin, then `/lens-doctor`. Doctor merges lens file directories into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.

## Usage

Tell the worker the **lens name**:

```text
Run the lens loop with lens=deck on these files …
```

The runner resolves `deck` → configured path. Omit `lens` to use `default_lens`.

On a terminal round it appends one `lens_run` (field `lens` = name) to `log_path`.

```text
/lens-close "my-deliverable-key" corrections=0
```

## Doctor

```text
/lens-doctor
```
