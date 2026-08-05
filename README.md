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
git checkout v0.1.1
rm -rf ~/.cursor/plugins/local/lens
mkdir -p ~/.cursor/plugins/local/lens
git archive v0.1.1 | tar -x -C ~/.cursor/plugins/local/lens
```

Then **Developer: Reload Window**, open any workspace, run `/lens-doctor`.

**Team Marketplace:** Cursor → Customize → Plugins → Import marketplace → `https://github.com/not-so-fat/lens` (or pin the `v0.1.1` tag), install `lens`, reload, `/lens-doctor`.

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

### Chat deliverables & explicit invocation

Enforcement normally fires on writes to `watch_globs` files. A deliverable produced **in the chat** (analysis, comparison, summary) writes no file, so the write gate can't see it. But on **Claude Code**, when you **explicitly ask for the lens** — e.g. `use yusuke lens`, `lens=deck`, `run the lens`, `with yusuke lens` — a `UserPromptSubmit` hook **arms** the session: the Stop hook then requires a `lens_run` for it, **regardless of writes**, and disarms once the run lands. Because a prompt-text arm is a heuristic, enforcement is warn-first — the first unsatisfied stop only warns, a later one blocks — and self-clearing (a 3-block circuit breaker + a 2 h TTL) so a false or abandoned arm can't wedge the session. So an explicit request is enforced for chat work too. (Negated/hedged mentions — "don't use the lens" — do not arm.)

Not yet on **Cursor** (no prompt-submit arming wired — tracked in [`docs/ISSUES.md`](docs/ISSUES.md) I-9); and a chat deliverable you did *not* explicitly flag is still not auto-enforced on either host. Set `"enforce": false` to pause all blocking.

## Doctor

```text
/lens-doctor
```

Doctor fails if Claude/Cursor hook commands are workspace-relative (`./python/...`) or if `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}` do not expand to real scripts under the plugin install.

### Runner access (out-of-workspace lens files)

The reviewer must read the lens files, which live outside the repo (`~/.lens/config.json` and the lens markdown in your vault). Interactive sessions approve those reads on prompt, but a **background** subagent can't prompt, so the review silently fails. Doctor pre-grants the access, per host, from your configured lens directories:

- **`cursor_sandbox`** — merges each lens dir into `~/.cursor/sandbox.json` `additionalReadonlyPaths`.
- **`claude_permissions`** — adds `Read(<lens dirs>/**)`, `Read(~/.lens/**)`, `Bash(python3 "${CLAUDE_PLUGIN_ROOT}/python/lens_append.py":*)` (plus a resolved-absolute variant of the same launcher), and `Bash(date:*)` to `~/.claude/settings.json` `permissions.allow`. The append launcher is a bare `python3 <path>` (no leading `PYTHONPATH=`) so a background reviewer subagent can run it without a prompt — Claude allow-rules don't match past an env-var assignment. Both grant forms are emitted so the match holds whether the permission matcher compares the command before or after `${CLAUDE_PLUGIN_ROOT}` expansion.

Both are written by `/lens-doctor` (fix mode); `--no-fix-sandbox` only reports gaps. Writing Claude grants widens auto-approve permissions, so if the agent's own run is blocked by a self-modification guard, run `/lens-doctor` yourself. (**Codex**: the equivalent — `writable_roots` / `sandbox_mode` — is deferred with the rest of the Codex port, see `docs/PRD.md`.)

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
