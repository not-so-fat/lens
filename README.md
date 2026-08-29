# Lens

Personal review standards for AI agents. One public repo installs on any Mac as a **Claude Code plugin**, a **Cursor plugin**, and **Codex support** (CLI + desktop), sharing config, contracts, and a JSONL run log. (The repo carries only plugin machinery — your lens *content* stays private in your own vault, never here.)

Canonical product + implementation spec: [`docs/PRD.md`](docs/PRD.md). Open implementation residuals: [`docs/ISSUES.md`](docs/ISSUES.md). Cutting a version: [`docs/RELEASE.md`](docs/RELEASE.md).

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

### Scoping the write gate (`ignore_globs` / `.lensignore`)

The write gate fires on every `watch_globs` match. Routine files (changelogs, notes, generated docs, tests) aren't review deliverables, so exclude them:

- **Global:** add `"ignore_globs": ["**/*.test.*", "notes/**"]` to `~/.lens/config.json`.
- **Per repo (committed, applies on every laptop):** drop a **`.lensignore`** in the repo root — gitignore-style, one glob per line, `#` comments. A slash-free line matches by basename anywhere (`CHANGELOG.md`); a line with a slash (`docs/**`) matches relative to the hook's `cwd` (normally the repo root). Only the **nearest** `.lensignore` walking up from `cwd` is read — patterns are not merged up the tree.

`node_modules`, `.git`, `dist`, `build`, `__pycache__`, and `.lens` are always ignored. Ignored files never trigger the gate; a real deliverable still does.

## Install

Lens is a **public GitHub marketplace**. Both hosts copy the plugin into their own
store (`~/.claude/plugins/cache/…` / Cursor's plugin dir), so **you keep no clone** —
there is nothing to move, and a relocated or deleted checkout can't break an install.

### Claude Code

```bash
claude plugin marketplace add not-so-fat/lens
claude plugin install lens@lens-plugins
```

New session should list the `lens` agent. Run `/lens-doctor`.

### Cursor (desktop IDE)

Cursor → Customize → Plugins → **Import marketplace** → `https://github.com/not-so-fat/lens`
(optionally pin a tag, e.g. `…/lens@v0.1.2`), install `lens`, then **Developer: Reload
Window** and run `/lens-doctor`. One import covers every workspace — no per-folder setup.

### Codex (CLI + desktop)

Codex has no marketplace, so its install is **doctor-managed**: from a checkout, run
`/lens-doctor` (or `python3 -m lens_lib doctor`) once. Doctor renders the reviewer
(`~/.codex/agents/lens.toml`) and the hooks (`~/.codex/hooks.json` — `Stop`,
`PostToolUse`, `UserPromptSubmit`) with **absolute** script paths, merging your existing
`~/.codex/hooks.json` non-destructively. It only touches `~/.codex/` if that directory
already exists, so a Codex-free machine is left alone. Re-run `/lens-doctor` after pulling
a new version to re-render the paths. The IDE extension is unsupported (hooks undocumented).

If you run Codex in `sandbox_mode = "workspace-write"`, add your log dir to
`writable_roots` so the worker can append the run log without an approval prompt —
`/lens-doctor`'s `codex_writable_roots` check prints the exact snippet.

### Updating

```bash
claude plugin marketplace update lens-plugins   # refresh the catalog from GitHub
claude plugin update lens@lens-plugins          # pull the new version
```

Cursor: re-import (or reload) the marketplace. Releases are versioned by the `version`
field in `plugin.json` / `marketplace.json`, so an update lands only after that version
is **bumped** — pushing commits alone won't change what `plugin update` sees (cutting a
release: [`docs/RELEASE.md`](docs/RELEASE.md)).

### Local development (plugin authors only)

To iterate without publishing:

**Claude Code** — add the repo itself as a `directory`-source marketplace:

```bash
claude plugin marketplace add /path/to/lens   # directory source — dev only
claude plugin install lens@lens-plugins
```

**Cursor** — no directory-source CLI exists; copy a checkout into Cursor's local plugin
dir (don't symlink outside that tree — Cursor rejects it), then **Developer: Reload Window**:

```bash
rm -rf ~/.cursor/plugins/local/lens && mkdir -p ~/.cursor/plugins/local/lens
git archive HEAD | tar -x -C ~/.cursor/plugins/local/lens   # or a pinned tag
```

The Claude Code `directory` source is the **only** install mode bound to a local path. If
you move or delete that repo, re-point it (`claude plugin marketplace add <new-path>`) and
rerun `/lens-doctor` — its `marketplace_source` check flags a stale directory source.
End-user marketplace installs above are never affected.

Hook commands use `${CURSOR_PLUGIN_ROOT}` (plugin install dir), **not** `./python/...` relative to your project. You do **not** copy hook scripts into each workspace — one plugin install covers every folder you open.

### Host contract (Cursor enforcement)

Cursor `stop` often has little/no transcript. Enforcement needs:

1. `afterFileEdit` recording writes (session / conversation id **and** preferably `workspace_roots`)
2. Matching ids (or the same workspace root) on `stop`
3. A logged `lens_run` after watched writes

If `afterFileEdit` omits workspace root **and** ids diverge from `stop`, enforcement can silently pass — treat workspace root on both hooks as required for reliability.

Writes are keyed by `(workspace, conversation_id)` so concurrent Agent chats in the same folder do not cross-trigger. Workspace-wide fallback applies only when the conversation/session id is missing.

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

Misses and noise from `/lens-close` append durable **correction signals** under `~/.lens/`. When the same gap shows up twice, propose a lens criteria update and apply it after review:

```bash
PYTHONPATH=python python3 -m lens_lib corrections list --lens review
PYTHONPATH=python python3 -m lens_lib corrections propose \
  --lens review --signal-ids cs_a,cs_b --ops-file ops.json --preview
PYTHONPATH=python python3 -m lens_lib corrections apply lp_…
```

Spec: [`docs/PRD_CORRECTION_CAPTURE.md`](docs/PRD_CORRECTION_CAPTURE.md).

### Chat deliverables & explicit invocation

Enforcement normally fires on writes to `watch_globs` files. A deliverable produced **in the chat** (analysis, comparison, summary) writes no file, so the write gate can't see it. But on **Claude Code and Codex**, when you **explicitly ask for the lens** — e.g. `use yusuke lens`, `lens=deck`, `run the lens`, `with yusuke lens` — a `UserPromptSubmit` hook **arms** the session: the Stop hook then requires a `lens_run` for it, **regardless of writes**, and disarms once the run lands. Because a prompt-text arm is a heuristic, enforcement is warn-first — the first unsatisfied stop only warns, a later one blocks — and self-clearing (a 3-block circuit breaker + a 2 h TTL) so a false or abandoned arm can't wedge the session. So an explicit request is enforced for chat work too. (Negated/hedged mentions — "don't use the lens" — do not arm.) A review that runs in a **sub-agent** still satisfies the parent session's gate: `append-run` credits any live armed session.

Not yet on **Cursor** (no prompt-submit arming wired — tracked in [`docs/ISSUES.md`](docs/ISSUES.md) I-9); and a chat deliverable you did *not* explicitly flag is still not auto-enforced on any host. Set `"enforce": false` to pause all blocking.

## Doctor

```text
/lens-doctor
```

Doctor fails if Claude/Cursor/Codex hook commands are workspace-relative (`./python/...`) or if `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}` / `${CODEX_PLUGIN_ROOT}` do not expand to real scripts. The `marketplace_source` check also fails when a `directory`-source lens marketplace (dev install) points at a moved/deleted path, and prints the re-point command. When `~/.codex/` exists, `codex_install` renders the reviewer + hooks into it and `codex_writable_roots` checks log-dir writability.

### Runner access (out-of-workspace lens files)

The reviewer must read the lens files, which live outside the repo (`~/.lens/config.json` and the lens markdown in your vault). Interactive sessions approve those reads on prompt, but a **background** subagent can't prompt, so the review silently fails. Doctor pre-grants the access, per host, from your configured lens directories:

- **`cursor_sandbox`** — merges each lens dir into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.
- **`codex_install` / `codex_writable_roots`** — renders the reviewer + hooks into `~/.codex/` (absolute paths) and, in `workspace-write` mode, checks the log dir is in `writable_roots` (Codex file reads are unrestricted, so lens files need no read-grant).
- **`claude_permissions`** — adds `Read(<lens dirs>/**)`, `Read(~/.lens/**)`, `Bash(python3 "${CLAUDE_PLUGIN_ROOT}/python/lens_append.py":*)` (plus a resolved-absolute variant of the same launcher), and `Bash(date:*)` to `~/.claude/settings.json` `permissions.allow`. The append launcher is a bare `python3 <path>` (no leading `PYTHONPATH=`) so a background reviewer subagent can run it without a prompt — Claude allow-rules don't match past an env-var assignment. Both grant forms are emitted so the match holds whether the permission matcher compares the command before or after `${CLAUDE_PLUGIN_ROOT}` expansion.

Both are written by `/lens-doctor` (fix mode); `--no-fix-sandbox` only reports gaps. Writing Claude grants widens auto-approve permissions, so if the agent's own run is blocked by a self-modification guard, run `/lens-doctor` yourself. (**Codex**: the equivalent is `codex_install` + `codex_writable_roots`, also written by `/lens-doctor` fix mode — see the Codex install section above and F6 in `docs/PRD.md`.)

## Unlocking Cursor stop follow-ups (`loop_limit`)

Cursor does **not** hard-block forever. The `stop` hook may send `followup_message` up to `loop_limit` times (default **5**). After that, the agent can stop even if no `lens_run` was logged (`hook_limit_exhausted` in the run log).

**Preferred unlock:** invoke the `lens` agent so a `lens_run` line is appended.

**Escape hatches:**

1. Set `"enforce": false` in `~/.lens/config.json` (disables blocking until you turn it back on).
2. Close the Agent chat / start a new conversation.
3. Temporarily remove or comment the lens `stop` entry (not recommended — use enforce=false).

The last forced follow-up message includes an unlock hint in the agent prompt.

## Manual Cursor smoke (I-4)

Automated tests mock hook payloads; they do not prove Cursor fires real `afterFileEdit` / `stop`. One-shot desktop check:

1. Install the Cursor plugin from this repo; run `/lens-doctor` (all green).
2. Point `default_lens` at `tests/fixtures/sample_lens.md` (absolute path) and a writable `log_path`.
3. In a **new** Agent chat in any workspace, ask:

   ```text
   Create a short file demo-lens-smoke.md in this workspace with one heading and
   two bullets. Do not run any lens. Stop when the file exists.
   ```

4. **Expect:** after the write, Cursor `stop` forces a follow-up mentioning the `lens` agent (and unlock hint). If the chat ends with no follow-up and `demo-lens-smoke.md` exists, check `log_path` for `hook_check` with `watched_writes` / `blocked`, and confirm plugin hooks use `${CURSOR_PLUGIN_ROOT}`.
5. Then: `Run the lens agent with lens=<your default>, deliverable="demo-lens-smoke", files=["demo-lens-smoke.md"]` — expect a `lens_run` line and a clean stop afterward.

Optional: dump the last few JSONL lines from `log_path` and confirm `host: "cursor"` and `session_ids` populated.

## Manual Codex smoke (I-11)

Automated tests mock hook payloads; they do not prove Codex fires real `PostToolUse` / `Stop`. One-shot CLI or desktop check:

1. Run `/lens-doctor` (all green, including `codex_install` and `codex_writable_roots`).
2. Point `default_lens` at `tests/fixtures/sample_lens.md` (absolute path) and a writable `log_path`.
3. In a **new** Codex session in any workspace, ask:

   ```text
   Create a short file demo-codex-smoke.md in this workspace with one heading and
   two bullets. Do not run any lens. Stop when the file exists.
   ```

4. **Expect:** `Stop` re-prompts with a block mentioning the `lens` agent. Check `log_path` for `hook_check` with `host: "codex"`, `wrote_watched: true`, `blocked: true`.
5. Then: `Run the lens agent with lens=<your default>, deliverable="demo-codex-smoke", files=["demo-codex-smoke.md"]` — expect a `lens_run` with `host: "codex"` and a clean stop afterward.
6. Edit the file again without running the lens — expect another block (fresh write batch).

**Arming check (optional):** in a new session, ask `use the <default_lens> lens on a chat summary` (no file write). Expect arming notice; `Stop` should block even with no watched writes until a `lens_run` lands.

**Replay helper** (installed hooks, appends real telemetry):  
`python3 .temporal/scripts/codex_live_smoke.py --session codex-smoke-<date>`

Payload/config assumptions: [`docs/ISSUES.md`](docs/ISSUES.md) I-11.
