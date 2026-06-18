from __future__ import annotations

from pathlib import Path

import pytest

from vscode_feature_scout import cli as _scout

SAMPLE_HTML = """
<!doctype html>
<html>
  <body>
    <main class="docs-main-content body">
      <h1>Visual Studio Code 1.125</h1>
      <h2>Integrated Browser</h2>
      <h3>Browse over remote connections (Preview)</h3>
      <p><strong>Setting</strong>: <span class="setting-link-main">workbench.browser.enableRemoteProxy</span></p>
      <p>When the integrated browser is opened in a remote workspace, HTTP(S) traffic can be proxied.</p>
      <h3>Web search from address bar</h3>
      <p>Use workbench.browser.searchEngine to choose a search engine.</p>
      <h2>Workbench</h2>
      <h3>New icon theme</h3>
      <p>A small color theme polish for the activity bar.</p>
      <h2>Agents</h2>
      <h3>Better agentic interaction with forwarded ports</h3>
      <p>If an agent requests a forwarded port, VS Code can rewrite the URL and notify the agent.</p>
      <h2>Thank you</h2>
      <p>Contributions mention MCP, Copilot, settings, terminal, and debug, but this is not adoption guidance.</p>
    </main>
  </body>
</html>
"""


def test_parse_release_notes_keeps_h2_context_and_setting_text() -> None:
    release_title, sections = _scout.parse_release_notes(SAMPLE_HTML)

    assert release_title == "Visual Studio Code 1.125"
    assert [section.title for section in sections] == [
        "Integrated Browser / Browse over remote connections (Preview)",
        "Integrated Browser / Web search from address bar",
        "Workbench / New icon theme",
        "Agents / Better agentic interaction with forwarded ports",
        "Thank you",
    ]
    assert "workbench.browser.enableRemoteProxy" in sections[0].text


def test_score_sections_prefers_agent_browser_remote_items(tmp_path: Path) -> None:
    profile = tmp_path / "profile.md"
    profile.write_text("Scout tags: codex, claude code, remote workspace, integrated browser\n", encoding="utf-8")
    _, sections = _scout.parse_release_notes(SAMPLE_HTML)

    candidates = _scout.score_sections(sections, _scout.load_keywords(profile), threshold=6)

    titles = [candidate.section.title for candidate in candidates]
    assert "Integrated Browser / Browse over remote connections (Preview)" in titles
    assert "Agents / Better agentic interaction with forwarded ports" in titles
    assert "Workbench / New icon theme" not in titles
    assert "Thank you" not in titles
    assert candidates[0].score >= candidates[-1].score


def test_keyword_matching_does_not_count_supported_as_port() -> None:
    assert _scout.keyword_matches("port", "forwarded ports are available")
    assert not _scout.keyword_matches("port", "supported policy keys")


def test_render_report_includes_budget_posture_and_actions(tmp_path: Path) -> None:
    profile = tmp_path / "profile.md"
    profile.write_text("Scout tags: integrated browser\n", encoding="utf-8")
    release_title, sections = _scout.parse_release_notes(SAMPLE_HTML)
    candidates = _scout.score_sections(sections, _scout.load_keywords(profile), threshold=6)

    report = _scout.render_report(
        release_title=release_title,
        source="sample",
        profile_path=profile,
        threshold=6,
        max_candidates=2,
        candidates=candidates,
    )

    assert "no full-repo scan" in report
    assert "workbench.browser.enableRemoteProxy" in report
    assert "Try it against local/remote app smoke checks" in report


def test_main_writes_report_and_state_then_skips_seen_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "release.html"
    output_path = tmp_path / "report.md"
    state_path = tmp_path / "state.json"
    profile_path = tmp_path / "profile.md"
    input_path.write_text(SAMPLE_HTML, encoding="utf-8")
    profile_path.write_text("Scout tags: integrated browser, remote workspace\n", encoding="utf-8")

    rc = _scout.main(
        [
            "--input",
            str(input_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--state",
            str(state_path),
        ]
    )

    assert rc == 0
    assert "Wrote" in capsys.readouterr().out
    assert output_path.exists()
    assert state_path.exists()

    rc = _scout.main(
        [
            "--input",
            str(input_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--state",
            str(state_path),
        ]
    )

    assert rc == 0
    assert "No new VS Code release notes" in capsys.readouterr().out


def test_main_regenerates_when_same_release_page_content_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "release.html"
    output_path = tmp_path / "report.md"
    state_path = tmp_path / "state.json"
    profile_path = tmp_path / "profile.md"
    input_path.write_text(SAMPLE_HTML, encoding="utf-8")
    profile_path.write_text("Scout tags: integrated browser, remote workspace\n", encoding="utf-8")

    assert (
        _scout.main(
            [
                "--input",
                str(input_path),
                "--profile",
                str(profile_path),
                "--output",
                str(output_path),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    capsys.readouterr()

    changed_html = SAMPLE_HTML.replace(
        "A small color theme polish for the activity bar.",
        "A small color theme polish plus a new agent setting for patch releases.",
    )
    input_path.write_text(changed_html, encoding="utf-8")

    assert (
        _scout.main(
            [
                "--input",
                str(input_path),
                "--profile",
                str(profile_path),
                "--output",
                str(output_path),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )

    assert "Wrote" in capsys.readouterr().out


def test_baseline_findings_detect_present_and_missing_capabilities(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("project routing", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude routing", encoding="utf-8")
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "code-reviewer.md").write_text("---\nname: code-reviewer\n---\n", encoding="utf-8")

    findings = _scout.collect_baseline_findings(repo=tmp_path, fetch_docs=False)
    by_key = {finding.capability.key: finding for finding in findings}

    assert by_key["custom-instructions"].adoption_state == "partially-present"
    assert by_key["custom-instructions"].repo_hits == ["AGENTS.md", "CLAUDE.md"]
    assert by_key["custom-agents"].adoption_state == "partially-present"
    assert ".claude/agents/code-reviewer.md" in by_key["custom-agents"].repo_hits
    assert by_key["mcp"].adoption_state == "not-wired"


def test_render_baseline_report_includes_docs_and_next_actions(tmp_path: Path) -> None:
    findings = _scout.collect_baseline_findings(repo=tmp_path, fetch_docs=False)

    report = _scout.render_baseline_report(repo=tmp_path, findings=findings, fetch_docs=False)

    assert "VS Code Feature Scout Baseline" in report
    assert "Official docs fetched: disabled" in report
    assert "Model Context Protocol" in report
    assert "safe status commands" in report
    assert "no full-repo scan" in report


def test_main_baseline_writes_report_without_fetching(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_path = tmp_path / "baseline.md"
    rc = _scout.main(
        [
            "--baseline",
            "--baseline-no-fetch",
            "--repo",
            str(tmp_path),
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    assert "Wrote" in capsys.readouterr().out
    assert "VS Code Feature Scout Baseline" in output_path.read_text(encoding="utf-8")
