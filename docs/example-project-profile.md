# Example Project Capability Profile

Scout tags: agents, mcp, integrated browser, remote workspace, terminal, tasks, python

Current project shape:

- Backend service with local tests and a browser-facing development UI.
- Coding agents use `AGENTS.md`, `CLAUDE.md`, or repository-specific prompt files.
- Generated reports should go under `outputs/`.
- Browser smoke checks, local ports, and remote workspaces are interesting adoption areas.

Useful constraints:

- Do not ask agents to read the whole repository just to evaluate VS Code changes.
- Prefer official VS Code docs and small trials before changing shared settings.
- Keep recommendations actionable enough to paste into Codex, Claude Code, Copilot, or a team issue.
