# VS Code Feature Scout

[Русская версия](README.ru.md)

VS Code is becoming an agent platform: custom instructions, custom agents, MCP
servers, browser tools, tasks, profiles, remote tunnels, model providers, and a
steady stream of new settings. The hard part is not reading every announcement.
The hard part is noticing which features are actually useful for your workflow.

**VS Code Feature Scout** is a tiny, dependency-free CLI that turns VS Code
release notes and existing VS Code capabilities into actionable recommendations.
It is designed to be cheap enough to run automatically and explicit enough to
hand its report to Codex, Claude Code, Copilot, or another coding agent.

## Intended Audience

Feature Scout is for:

- solo developers who live in VS Code, use AI agents, and do not want to read
  every VS Code release note manually;
- teams with `AGENTS.md`, `CLAUDE.md`, MCP, custom prompts, or custom agents who
  want editor capabilities to become part of agent context;
- maintainers who want a small, repeatable report instead of relying on whoever
  happened to notice a new VS Code feature.

## What It Does

Feature Scout has two complementary modes:

- **Release mode** checks the latest VS Code release notes and reports new items
  that match your project profile.
- **Baseline mode** inventories existing VS Code capabilities that may already
  be useful, even if they were introduced months ago.

It writes Markdown reports such as:

```text
outputs/vscode_feature_scout/latest.md
outputs/vscode_feature_scout/baseline.md
```

The reports are intentionally short and action-oriented:

- feature name;
- why it may matter;
- relevant settings;
- concrete repo signals;
- the smallest safe next action.

## Typical Agent Loop

The intended loop is deliberately simple:

1. VS Code starts, restarts, or updates.
2. The optional LaunchAgent runs Feature Scout.
3. Feature Scout writes `latest.md` or `baseline.md`.
4. Codex, Claude Code, Copilot, Continue, or another agent reads that report as
   compact context.
5. The agent adapts project instructions, prompts, tasks, or MCP configuration
   only when the report shows a useful and relevant capability.

## Example Output

Shortened baseline report snippet:

```markdown
### Integrated Browser Tools

- Priority: high
- Adoption state: candidate
- Repo signals: none
- Settings: `workbench.browser.enableChatTools`, `workbench.browser.enableRemoteProxy`
- Why it matters: Browser tools can turn local API/UI smoke checks into
  agent-visible page, console, screenshot, and click flows.
- Next action: Trial browser tools on one local smoke path before changing
  shared settings.
```

Shortened release report snippet:

```markdown
### Integrated Browser / Browse over remote connections (Preview)

- Score: 20
- Keyword hits: `integrated browser`, `remote`, `workbench.browser`
- Settings: `workbench.browser.enableRemoteProxy`
- Suggested actions:
  - Try it against local/remote app smoke checks before changing shared settings.
  - Evaluate this setting key explicitly: `workbench.browser.enableRemoteProxy`.
```

## Why This Exists

Modern IDE features often land faster than team workflows can absorb them. A
developer may notice a new setting like `workbench.browser.enableRemoteProxy`,
but miss older capabilities such as MCP servers, browser tools, custom agents,
prompt files, or task automation.

This creates a quiet gap:

- AI agents do not know which IDE capabilities they can use.
- Project docs mention workflows but not the editor features that could improve
  them.
- Teams either ignore useful features or adopt them too broadly without a small
  trial.

Feature Scout fills that gap. It acts as a lightweight translator between VS
Code capabilities and your project workflow.

## Why Not Just Read Release Notes?

You still can. Feature Scout is useful when release notes are not enough:

- release notes are global; Feature Scout filters them through your project
  profile;
- release notes do not know whether your repo already has `AGENTS.md`,
  `.vscode/mcp.json`, `.vscode/tasks.json`, or custom agents;
- `state.json` lets automation skip unchanged releases;
- baseline mode catches older VS Code capabilities that are no longer "new" but
  may still be valuable;
- the output is already shaped as a small Markdown handoff for AI agents.

## Design Principles

- **No full-repo scan.** The scout reads a compact project profile and checks a
  short list of concrete signals.
- **No LLM required.** Reports are generated with deterministic, local Python.
- **Official-docs first.** Baseline mode uses curated official VS Code docs.
- **Small next steps.** It suggests trials and explicit settings, not sweeping
  rewrites.
- **Safe automation.** The optional macOS LaunchAgent can run on VS Code
  start/update events without polling every minute.

Concrete repo signals are intentionally boring and explicit. Baseline mode
checks paths such as:

- `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`;
- `.claude/agents/`, `.github/prompts/`, `.vscode/prompts/`;
- `.vscode/mcp.json`, `.mcp.json`;
- `.vscode/tasks.json`, `.devcontainer/devcontainer.json`.

## Install

Clone the repository:

```bash
git clone https://github.com/Andrej-Ilin/vscode-feature-scout.git
cd vscode-feature-scout
```

Run from source with `uv`:

```bash
uv run vscode-feature-scout --help
```

Or install editable:

```bash
python -m pip install -e .
vscode-feature-scout --help
```

## Quick Start

Create a compact project profile:

```bash
mkdir -p docs/tooling
cat > docs/tooling/project_capability_profile.md <<'EOF'
# Project Capability Profile

Scout tags: agents, mcp, integrated browser, remote workspace, terminal, tasks, python

Current project shape:

- Python service with local tests and a browser-facing UI.
- Agents use AGENTS.md and project-specific review prompts.
- Generated reports belong under outputs/.
EOF
```

There is also a fuller example in
[`docs/example-project-profile.md`](docs/example-project-profile.md).

Run release mode:

```bash
vscode-feature-scout \
  --profile docs/tooling/project_capability_profile.md \
  --output outputs/vscode_feature_scout/latest.md
```

Run baseline mode:

```bash
vscode-feature-scout \
  --baseline \
  --repo . \
  --output outputs/vscode_feature_scout/baseline.md
```

Print a report for an agent prompt:

```bash
vscode-feature-scout --baseline --output -
```

## Release Mode

Release mode fetches:

```text
https://code.visualstudio.com/updates
```

It parses release-note sections and scores them against:

- built-in keywords such as `agent`, `mcp`, `integrated browser`, `remote`,
  `task`, `debug`, `model provider`;
- `Scout tags:` from your project profile;
- setting keys found in the release notes.

Example:

```bash
vscode-feature-scout --include-seen
```

By default, state is stored under:

```text
outputs/vscode_feature_scout/state.json
```

If the latest release page has not changed, the command exits quickly.

## Baseline Mode

Baseline mode answers a different question:

> What useful VS Code capabilities already exist, and are we using them?

It checks a curated list of official VS Code capabilities:

- Custom Instructions
- Custom Agents
- Model Context Protocol (MCP)
- Integrated Browser Tools
- Prompt Files and Slash Commands
- Agent Skills
- Tasks
- Profiles
- Remote Tunnels and Remote Workspaces

For each capability it reports:

- priority;
- adoption state (`not-wired`, `candidate`, `partially-present`);
- official documentation URL;
- repo signals such as `AGENTS.md`, `.claude/agents/`, `.vscode/mcp.json`,
  `.vscode/tasks.json`;
- recommended next action.

Run without fetching docs, useful for tests or offline environments:

```bash
vscode-feature-scout --baseline --baseline-no-fetch
```

## macOS LaunchAgent

Feature Scout includes an optional macOS LaunchAgent installer. It can run the
scout when VS Code starts/restarts or when the app metadata changes after an
update.

Install Feature Scout in a stable Python environment before enabling the
LaunchAgent. The generated plist stores the Python interpreter path used by
`vscode-feature-scout-launchd`.

Install and load:

```bash
vscode-feature-scout-launchd --install --load --repo /path/to/your/project
```

This writes:

```text
~/Library/LaunchAgents/dev.vscode-feature-scout.plist
```

By default it uses `WatchPaths`, not polling:

- `~/Library/Application Support/Code/logs`
- `/Applications/Visual Studio Code.app/Contents/Info.plist`
- `~/Applications/Visual Studio Code.app/Contents/Info.plist`

Status:

```bash
vscode-feature-scout-launchd --status
```

Uninstall:

```bash
vscode-feature-scout-launchd --uninstall
```

If you want a fallback poll interval:

```bash
vscode-feature-scout-launchd --install --load --repo /path/to/your/project --poll-interval 300
```

## Good First Use Cases

Feature Scout is especially useful when:

- you use coding agents and want them to understand editor capabilities;
- you maintain `AGENTS.md`, `CLAUDE.md`, custom prompts, or MCP configuration;
- your project has local UI/API smoke checks that could benefit from VS Code
  browser tools;
- you want a lightweight "what changed in VS Code?" report after updates;
- you want a baseline inventory before adopting MCP, custom agents, or tasks.

## What It Does Not Do

- It does not run an LLM.
- It does not send your repository contents anywhere.
- It does not inspect databases, secrets, raw data, or private files.
- It does not automatically change VS Code settings.
- It does not replace a human decision about adopting a workflow.

## Development

Run tests:

```bash
uv run --extra dev python -m pytest -q
```

Run lint:

```bash
uv run --extra dev python -m ruff check src tests
uv run --extra dev python -m ruff format --check src tests
```

## License

MIT
