#!/usr/bin/env python
"""Find VS Code release-note items that may improve a project's AI workflow.

The scout is intentionally cheap: it reads one VS Code release page, scores
small release-note sections against a compact project capability profile, and
writes a short Markdown report. It must not read the full repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_SOURCE_URL = "https://code.visualstudio.com/updates"
DEFAULT_PROFILE_PATH = Path("docs") / "tooling" / "project_capability_profile.md"
DEFAULT_OUTPUT_PATH = Path("outputs") / "vscode_feature_scout" / "latest.md"
DEFAULT_BASELINE_OUTPUT_PATH = Path("outputs") / "vscode_feature_scout" / "baseline.md"
DEFAULT_STATE_PATH = Path("outputs") / "vscode_feature_scout" / "state.json"

SETTING_RE = re.compile(r"\b(?:[a-z][a-z0-9_-]*\.)+[A-Za-z][A-Za-z0-9_-]*\b")
SCOUT_TAGS_RE = re.compile(r"^Scout tags:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

DEFAULT_KEYWORDS: dict[str, int] = {
    "agent": 5,
    "agents": 5,
    "mcp": 6,
    "copilot": 4,
    "language model": 4,
    "model provider": 4,
    "integrated browser": 6,
    "workbench.browser": 6,
    "remote": 5,
    "remote connection": 5,
    "forwarded port": 5,
    "port": 3,
    "dev container": 5,
    "ssh": 4,
    "tunnel": 4,
    "terminal": 4,
    "task": 3,
    "debug": 3,
    "workspace": 3,
    "settings": 2,
    "setting": 1,
    "extension": 2,
    "profile": 2,
    "python": 2,
    "notebook": 2,
    "security": 3,
    "policy": 2,
    "enterprise": 1,
    "auto-update": 2,
}
EXCLUDED_SECTION_TITLES = {"thank you"}


@dataclass
class Section:
    title: str
    level: int
    body: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return normalize_ws(" ".join([self.title, *self.body]))


@dataclass
class Candidate:
    section: Section
    score: int
    keyword_hits: list[str]
    settings: list[str]


@dataclass(frozen=True)
class BaselineCapability:
    key: str
    title: str
    url: str
    priority: str
    why: str
    next_action: str
    settings: tuple[str, ...] = ()
    signal_paths: tuple[str, ...] = ()
    signal_globs: tuple[str, ...] = ()


@dataclass
class BaselineFinding:
    capability: BaselineCapability
    adoption_state: str
    repo_hits: list[str]
    docs_status: str
    docs_title: str


BASELINE_CAPABILITIES: tuple[BaselineCapability, ...] = (
    BaselineCapability(
        key="custom-instructions",
        title="Custom Instructions",
        url="https://code.visualstudio.com/docs/copilot/customization/custom-instructions",
        priority="high",
        why="VS Code can use repo instructions such as AGENTS.md/CLAUDE.md to steer agent behavior.",
        next_action="Keep AGENTS.md as the source of truth; only add VS Code-specific notes when behavior diverges.",
        signal_paths=("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"),
    ),
    BaselineCapability(
        key="custom-agents",
        title="Custom Agents",
        url="https://code.visualstudio.com/docs/agent-customization/custom-agents",
        priority="high",
        why="VS Code custom agents can make recurring review, scouting, and project-maintenance roles explicit.",
        next_action="Start with one narrow reviewer or project-scout agent before modeling a whole team of agents.",
        signal_paths=(".claude/agents",),
        signal_globs=(".claude/agents/*.md",),
    ),
    BaselineCapability(
        key="mcp",
        title="Model Context Protocol (MCP)",
        url="https://code.visualstudio.com/docs/agent-customization/mcp-servers",
        priority="high",
        why="MCP can expose safe local tooling to VS Code agents without asking them to read the whole repo.",
        next_action="Create a read-only MCP draft for project maps, scout reports, and safe status commands.",
        signal_paths=(".vscode/mcp.json", ".mcp.json"),
    ),
    BaselineCapability(
        key="integrated-browser-tools",
        title="Integrated Browser Tools",
        url="https://code.visualstudio.com/docs/debugtest/integrated-browser",
        priority="high",
        why="Browser tools can turn local API/UI smoke checks into agent-visible page, console, screenshot, and click flows.",
        next_action="Trial browser tools on one local smoke path before changing shared settings.",
        settings=(
            "workbench.browser.enableChatTools",
            "workbench.browser.openLocalhostLinks",
            "workbench.browser.enableRemoteProxy",
        ),
    ),
    BaselineCapability(
        key="prompt-files",
        title="Prompt Files and Slash Commands",
        url="https://code.visualstudio.com/docs/copilot/customization/prompt-files",
        priority="medium",
        why="Prompt files can make stage starters and review prompts reusable inside VS Code.",
        next_action="Convert only stable prompts, such as review-cleanup or stage starter templates, after they settle.",
        signal_paths=(".github/prompts", ".vscode/prompts", ".claude/commands"),
        signal_globs=(".claude/commands/*.md",),
    ),
    BaselineCapability(
        key="agent-skills",
        title="Agent Skills",
        url="https://code.visualstudio.com/docs/agent-customization/agent-skills",
        priority="medium",
        why="Agent Skills overlap with Codex skills and can package repeatable workflows for VS Code agents.",
        next_action="Do not duplicate every local workflow; package only stable, repeatable agent routines first.",
        signal_paths=(".vscode/skills", ".github/skills"),
    ),
    BaselineCapability(
        key="tasks",
        title="Tasks",
        url="https://code.visualstudio.com/docs/debugtest/tasks",
        priority="medium",
        why="Tasks can provide manual VS Code buttons for scout, focused tests, OpenAPI dump, and smoke checks.",
        next_action="Add tasks only for commands we run often; avoid using folderOpen as a global trigger.",
        signal_paths=(".vscode/tasks.json",),
    ),
    BaselineCapability(
        key="profiles",
        title="Profiles",
        url="https://code.visualstudio.com/docs/configure/profiles",
        priority="low",
        why="Profiles can separate AI-heavy, presentation, and backend-focused VS Code setups.",
        next_action="Keep as optional personal setup; do not commit profile assumptions to the repo.",
    ),
    BaselineCapability(
        key="remote-tunnels",
        title="Remote Tunnels and Remote Workspaces",
        url="https://code.visualstudio.com/docs/remote/tunnels",
        priority="low",
        why="Remote workspaces become useful if we move local services or GPU/LLM workloads off this Mac.",
        next_action="Revisit when devcontainer/SSH/GPU workflow becomes active.",
        signal_paths=(".devcontainer/devcontainer.json",),
    ),
)


class ReleaseNotesParser(HTMLParser):
    """Extract h2/h3 release-note sections from code.visualstudio.com HTML."""

    HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
    BLOCK_TAGS = {"p", "li", "pre"}
    SKIP_TAGS = {"script", "style", "svg", "button", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_content = False
        self.skip_depth = 0
        self.release_title = ""
        self.current_h2 = ""
        self.current_section: Section | None = None
        self.sections: list[Section] = []
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.block_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        classes = attrs.get("class", "")

        if tag == "main" and "docs-main-content" in classes:
            self.in_content = True
            return

        if not self.in_content:
            return

        if self.skip_depth:
            self.skip_depth += 1
            return

        role = attrs.get("role", "")
        if (
            tag in self.SKIP_TAGS
            or role == "menuitem"
            or "setting-dropdown-menu" in classes
            or "sr-only" in classes
            or "badge-org" in classes
        ):
            self.skip_depth = 1
            return

        if tag in self.HEADING_TAGS:
            self._flush_block()
            self.heading_level = self.HEADING_TAGS[tag]
            self.heading_parts = []
            return

        if tag in self.BLOCK_TAGS:
            self._flush_block()
            self.block_parts = []
            return

        if tag == "br":
            self._append_text(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_content:
            return

        if self.skip_depth:
            self.skip_depth -= 1
            return

        if tag in self.HEADING_TAGS and self.heading_level is not None:
            title = normalize_ws(" ".join(self.heading_parts))
            self._start_section(title, self.heading_level)
            self.heading_level = None
            self.heading_parts = []
            return

        if tag in self.BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if not self.in_content or self.skip_depth:
            return
        self._append_text(data)

    def _append_text(self, data: str) -> None:
        text = unescape(data)
        if self.heading_level is not None:
            self.heading_parts.append(text)
        elif self.block_parts is not None:
            self.block_parts.append(text)

    def _start_section(self, title: str, level: int) -> None:
        if not title:
            return

        if level == 1:
            self.release_title = title
            self.current_section = None
            return

        if level == 2:
            self.current_h2 = title
            self.current_section = Section(title=title, level=level)
            self.sections.append(self.current_section)
            return

        section_title = f"{self.current_h2} / {title}" if self.current_h2 else title
        self.current_section = Section(title=section_title, level=level)
        self.sections.append(self.current_section)

    def _flush_block(self) -> None:
        if self.block_parts is None:
            return
        block = normalize_ws(" ".join(self.block_parts))
        if block and self.current_section is not None:
            self.current_section.body.append(block)
        self.block_parts = None


def normalize_ws(value: str) -> str:
    return " ".join(value.split())


def parse_release_notes(html: str) -> tuple[str, list[Section]]:
    parser = ReleaseNotesParser()
    parser.feed(html)
    parser.close()
    sections = [section for section in parser.sections if section.body]
    return parser.release_title or "Visual Studio Code release notes", sections


def load_keywords(profile_path: Path) -> dict[str, int]:
    keywords = dict(DEFAULT_KEYWORDS)
    if not profile_path.exists():
        return keywords

    text = profile_path.read_text(encoding="utf-8")
    match = SCOUT_TAGS_RE.search(text)
    if not match:
        return keywords

    for raw_tag in match.group(1).split(","):
        tag = normalize_ws(raw_tag).lower()
        if tag:
            keywords[tag] = max(keywords.get(tag, 0), 3)
    return keywords


def score_sections(sections: list[Section], keywords: dict[str, int], threshold: int) -> list[Candidate]:
    candidates: list[Candidate] = []

    for section in sections:
        if section.title.lower() in EXCLUDED_SECTION_TITLES:
            continue

        lower_text = section.text.lower()
        hits: list[str] = []
        score = 0
        for keyword, weight in keywords.items():
            if keyword_matches(keyword, lower_text):
                hits.append(keyword)
                score += weight

        settings = sorted(set(SETTING_RE.findall(section.text)))
        score += 2 * len(settings)

        if score >= threshold:
            candidates.append(Candidate(section=section, score=score, keyword_hits=sorted(hits), settings=settings))

    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.section.title))


def keyword_matches(keyword: str, lower_text: str) -> bool:
    keyword = keyword.lower()
    if re.fullmatch(r"[a-z0-9]+", keyword):
        return re.search(rf"\b{re.escape(keyword)}s?\b", lower_text) is not None
    return keyword in lower_text


def suggested_actions(candidate: Candidate) -> list[str]:
    text = candidate.section.text.lower()
    actions: list[str] = []

    if any(term in text for term in ["integrated browser", "workbench.browser", "remote", "forwarded port"]):
        actions.append("Try it against local/remote app smoke checks before changing shared settings.")

    if any(term in text for term in ["agent", "mcp", "language model", "model provider", "copilot"]):
        actions.append("Review Codex/Claude routing docs and decide whether AGENTS.md needs a workflow note.")

    if any(term in text for term in ["terminal", "task", "debug"]):
        actions.append("Check whether .vscode tasks/debug config can remove manual setup steps.")

    if any(term in text for term in ["security", "policy", "enterprise", "privacy"]):
        actions.append(
            "Route policy/privacy-sensitive changes through the project security or privacy owner before adopting."
        )

    if candidate.settings:
        joined = ", ".join(f"`{setting}`" for setting in candidate.settings)
        actions.append(f"Evaluate these setting keys explicitly: {joined}.")

    if not actions:
        actions.append("Ask Codex or Claude Code to inspect only the directly affected workflow files.")

    return actions[:4]


def render_report(
    *,
    release_title: str,
    source: str,
    profile_path: Path,
    threshold: int,
    max_candidates: int,
    candidates: list[Candidate],
) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    shown = candidates[:max_candidates]
    lines = [
        "# VS Code Feature Scout Report",
        "",
        f"- Generated: {now}",
        f"- Source: {source}",
        f"- Release: {release_title}",
        f"- Project profile: {profile_path}",
        f"- Scoring threshold: {threshold}",
        "- Token posture: release sections + compact project profile only; no full-repo scan.",
        "",
    ]

    if not shown:
        lines.extend(
            [
                "## No Above-Threshold Candidates",
                "",
                "No release-note sections matched the current project capability profile strongly enough.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["## High-Signal Candidates", ""])
    for index, candidate in enumerate(shown, start=1):
        summary = shorten(candidate.section.text, 750)
        hit_text = ", ".join(f"`{hit}`" for hit in candidate.keyword_hits) or "none"
        settings_text = ", ".join(f"`{setting}`" for setting in candidate.settings) or "none"

        lines.extend(
            [
                f"### {index}. {candidate.section.title}",
                "",
                f"- Score: {candidate.score}",
                f"- Keyword hits: {hit_text}",
                f"- Settings: {settings_text}",
                "- Suggested actions:",
            ]
        )
        lines.extend(f"  - {action}" for action in suggested_actions(candidate))
        lines.extend(["", "Summary:", "", summary, ""])

    if len(candidates) > len(shown):
        lines.append(f"_Skipped {len(candidates) - len(shown)} lower-ranked candidates due to --max-candidates._")
        lines.append("")

    return "\n".join(lines)


def shorten(text: str, limit: int) -> str:
    text = normalize_ws(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def fetch_url(url: str) -> tuple[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "vscode-feature-scout/0.1 (+https://code.visualstudio.com/updates)",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - official HTTPS URL or user-provided scout input.
        body = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
    return final_url, body


def first_heading_from_html(html: str) -> str:
    title, sections = parse_release_notes(html)
    if title != "Visual Studio Code release notes":
        return title
    return sections[0].title if sections else "unknown"


def repo_signal_hits(repo: Path, capability: BaselineCapability) -> list[str]:
    hits: list[str] = []
    for raw_path in capability.signal_paths:
        path = repo / raw_path
        if path.exists():
            hits.append(raw_path)
    for pattern in capability.signal_globs:
        for path in sorted(repo.glob(pattern)):
            if path.exists():
                hits.append(path.relative_to(repo).as_posix())
    return sorted(set(hits))


def adoption_state(capability: BaselineCapability, hits: list[str]) -> str:
    if capability.key in {"integrated-browser-tools", "profiles"}:
        return "candidate"
    if hits:
        return "partially-present"
    return "not-wired"


def collect_baseline_findings(
    *,
    repo: Path,
    fetch_docs: bool,
    capabilities: tuple[BaselineCapability, ...] = BASELINE_CAPABILITIES,
) -> list[BaselineFinding]:
    findings: list[BaselineFinding] = []
    for capability in capabilities:
        docs_status = "not fetched"
        docs_title = "not fetched"
        if fetch_docs:
            try:
                final_url, html = fetch_url(capability.url)
            except Exception as exc:  # pragma: no cover - network failures vary by host.
                docs_status = f"fetch failed: {exc.__class__.__name__}"
                docs_title = "unknown"
            else:
                docs_status = f"ok: {final_url}"
                docs_title = first_heading_from_html(html)

        hits = repo_signal_hits(repo, capability)
        findings.append(
            BaselineFinding(
                capability=capability,
                adoption_state=adoption_state(capability, hits),
                repo_hits=hits,
                docs_status=docs_status,
                docs_title=docs_title,
            )
        )
    priority_order = {"high": 0, "medium": 1, "low": 2}
    state_order = {"not-wired": 0, "candidate": 1, "partially-present": 2}
    return sorted(
        findings,
        key=lambda finding: (
            priority_order.get(finding.capability.priority, 9),
            state_order.get(finding.adoption_state, 9),
            finding.capability.title,
        ),
    )


def render_baseline_report(*, repo: Path, findings: list[BaselineFinding], fetch_docs: bool) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    fetched_count = sum(1 for finding in findings if finding.docs_status.startswith("ok:"))
    lines = [
        "# VS Code Feature Scout Baseline",
        "",
        f"- Generated: {now}",
        f"- Repo: {repo}",
        f"- Official docs fetched: {fetched_count}/{len(findings)}"
        if fetch_docs
        else "- Official docs fetched: disabled",
        "- Token posture: curated capability inventory + concrete repo signals only; no full-repo scan.",
        "",
        "## Findings",
        "",
    ]

    for index, finding in enumerate(findings, start=1):
        capability = finding.capability
        settings = ", ".join(f"`{setting}`" for setting in capability.settings) or "none"
        repo_hits = ", ".join(f"`{hit}`" for hit in finding.repo_hits) or "none"
        lines.extend(
            [
                f"### {index}. {capability.title}",
                "",
                f"- Priority: {capability.priority}",
                f"- Adoption state: {finding.adoption_state}",
                f"- Official doc: {capability.url}",
                f"- Docs status: {finding.docs_status}",
                f"- Docs title: {finding.docs_title}",
                f"- Repo signals: {repo_hits}",
                f"- Settings: {settings}",
                f"- Why it matters: {capability.why}",
                f"- Next action: {capability.next_action}",
                "",
            ]
        )

    return "\n".join(lines)


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, *, source: str, release_title: str, content_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "release_title": release_title,
        "content_sha256": content_sha256,
        "seen_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def release_fingerprint(release_title: str, sections: list[Section]) -> str:
    parts = [release_title]
    for section in sections:
        parts.append(section.text)
    return content_hash("\n".join(parts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Generate a baseline inventory of existing VS Code capabilities, not just latest release notes.",
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="VS Code updates URL to fetch.")
    parser.add_argument("--input", type=Path, help="Read release-note HTML from a local file instead of fetching.")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repo path for baseline signal checks.")
    parser.add_argument(
        "--profile", type=Path, default=DEFAULT_PROFILE_PATH, help="Compact project capability profile."
    )
    parser.add_argument("--output", type=Path, default=None, help="Markdown report path, or '-' for stdout.")
    parser.add_argument(
        "--state", type=Path, default=DEFAULT_STATE_PATH, help="State file used to detect already-seen releases."
    )
    parser.add_argument(
        "--baseline-no-fetch", action="store_true", help="Do not fetch official docs in --baseline mode."
    )
    parser.add_argument("--no-state", action="store_true", help="Do not read or update the state file.")
    parser.add_argument("--include-seen", action="store_true", help="Regenerate even if the release was already seen.")
    parser.add_argument("--threshold", type=int, default=6, help="Minimum relevance score for a section.")
    parser.add_argument("--max-candidates", type=int, default=8, help="Maximum candidates to include in the report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.output or (DEFAULT_BASELINE_OUTPUT_PATH if args.baseline else DEFAULT_OUTPUT_PATH)

    if args.baseline:
        repo = args.repo.resolve()
        findings = collect_baseline_findings(repo=repo, fetch_docs=not args.baseline_no_fetch)
        report = render_baseline_report(repo=repo, findings=findings, fetch_docs=not args.baseline_no_fetch)
        if str(output_path) == "-":
            print(report)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report + "\n", encoding="utf-8")
            print(f"Wrote {output_path}")
        return 0

    if args.input:
        source = str(args.input)
        html = args.input.read_text(encoding="utf-8")
    else:
        source, html = fetch_url(args.source_url)

    release_title, sections = parse_release_notes(html)
    if not sections:
        print("ERROR: no release-note sections found in source.", file=sys.stderr)
        return 1
    source_hash = release_fingerprint(release_title, sections)

    if not args.no_state and not args.include_seen:
        state = load_state(args.state)
        if (
            state.get("source") == source
            and state.get("release_title") == release_title
            and state.get("content_sha256") == source_hash
        ):
            print(f"No new VS Code release notes since {release_title}. Use --include-seen to regenerate.")
            return 0

    keywords = load_keywords(args.profile)
    candidates = score_sections(sections, keywords, args.threshold)
    report = render_report(
        release_title=release_title,
        source=source,
        profile_path=args.profile,
        threshold=args.threshold,
        max_candidates=args.max_candidates,
        candidates=candidates,
    )

    if str(output_path) == "-":
        print(report)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report + "\n", encoding="utf-8")
        print(f"Wrote {output_path}")

    if not args.no_state:
        save_state(args.state, source=source, release_title=release_title, content_sha256=source_hash)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
