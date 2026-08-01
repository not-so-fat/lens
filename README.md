# Lens

Personal review standards for AI agents. One private repo installs on any Mac as a **Claude Code plugin** and a **Cursor plugin**, sharing config, contracts, and a JSONL run log.

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

## Install — Claude Code

```bash
claude plugin marketplace add not-so-fat/lens   # or local path / git URL
claude plugin install lens@lens-plugins
```

New session should list the `lens` agent. Run `/lens-doctor`.

## Install — Cursor (desktop IDE)

**Local (verified):** pin a tag, copy into Cursor’s local plugins dir (do not symlink outside that tree — Cursor rejects it), reload, then doctor:

```bash
git clone https://github.com/not-so-fat/lens.git /tmp/lens && cd /tmp/lens
git checkout v0.1.0
rm -rf ~/.cursor/plugins/local/lens
mkdir -p ~/.cursor/plugins/local/lens
git archive v0.1.0 | tar -x -C ~/.cursor/plugins/local/lens
```

Then **Developer: Reload Window**, open any workspace, run `/lens-doctor`.

**Team Marketplace:** Cursor → Customize → Plugins → Import marketplace → `https://github.com/not-so-fat/lens` (or pin the `v0.1.0` tag), install `lens`, reload, `/lens-doctor`.

Hook commands use `${CURSOR_PLUGIN_ROOT}` (plugin install dir), **not** `./python/...` relative to your project. You do **not** copy hook scripts into each workspace — one plugin install covers every folder you open.

Doctor merges lens file directories into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.

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

## Doctor

```text
/lens-doctor
```

Doctor fails if Claude/Cursor hook commands are workspace-relative (`./python/...`) or if `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}` do not expand to real scripts under the plugin install.

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
