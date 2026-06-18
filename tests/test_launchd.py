from __future__ import annotations

from pathlib import Path

from vscode_feature_scout import launchd as _install
from vscode_feature_scout import watch as _watch


def test_build_plist_uses_absolute_repo_and_module_invocation(tmp_path: Path) -> None:
    payload = _install.build_plist(
        label="dev.test.vscode-feature-scout",
        repo=tmp_path,
        poll_interval=0,
        watch_paths=[tmp_path / "Code" / "logs", tmp_path / "Code.app" / "Contents" / "Info.plist"],
    )

    assert payload["Label"] == "dev.test.vscode-feature-scout"
    assert "StartInterval" not in payload
    assert payload["RunAtLoad"] is True
    assert payload["WatchPaths"] == [
        str(tmp_path / "Code" / "logs"),
        str(tmp_path / "Code.app" / "Contents" / "Info.plist"),
    ]
    assert payload["WorkingDirectory"] == str(tmp_path)
    assert payload["ProgramArguments"][1:3] == ["-m", "vscode_feature_scout.watch"]
    assert payload["ProgramArguments"][-2:] == ["--repo", str(tmp_path)]
    assert payload["StandardOutPath"].endswith("dev.test.vscode-feature-scout.out.log")


def test_build_plist_keeps_optional_poll_interval(tmp_path: Path) -> None:
    payload = _install.build_plist(
        label="dev.test.vscode-feature-scout",
        repo=tmp_path,
        poll_interval=300,
        watch_paths=[tmp_path / "logs"],
    )

    assert payload["StartInterval"] == 300


def test_watch_noops_when_code_is_not_running_and_version_unknown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_watch, "find_code_pid", lambda: None)
    monkeypatch.setattr(_watch, "vscode_version", lambda paths: "unknown")
    called = False

    def _run_scout(repo: Path) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(_watch, "run_scout", _run_scout)

    rc = _watch.check_once(tmp_path, tmp_path / "state.json", [])

    assert rc == 0
    assert called is False


def test_watch_runs_scout_once_per_new_process_identity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_watch, "find_code_pid", lambda: "123")
    monkeypatch.setattr(_watch, "process_started_at", lambda pid: "Thu Jun 18 10:00:00 2026")
    monkeypatch.setattr(_watch, "vscode_version", lambda paths: "1.125.0")
    calls: list[Path] = []

    def _run_scout(repo: Path) -> int:
        calls.append(repo)
        return 0

    monkeypatch.setattr(_watch, "run_scout", _run_scout)
    state = tmp_path / "state.json"

    assert _watch.check_once(tmp_path, state, []) == 0
    assert _watch.check_once(tmp_path, state, []) == 0

    assert calls == [tmp_path]
    state_text = state.read_text(encoding="utf-8")
    assert '"last_reason": "version,process"' in state_text
    assert '"last_vscode_version": "1.125.0"' in state_text


def test_watch_runs_scout_once_per_app_version_change_without_code_process(monkeypatch, tmp_path: Path) -> None:
    versions = iter(["1.125.0", "1.125.0", "1.126.0"])
    monkeypatch.setattr(_watch, "find_code_pid", lambda: None)
    monkeypatch.setattr(_watch, "vscode_version", lambda paths: next(versions))
    calls: list[Path] = []

    def _run_scout(repo: Path) -> int:
        calls.append(repo)
        return 0

    monkeypatch.setattr(_watch, "run_scout", _run_scout)
    state = tmp_path / "state.json"

    assert _watch.check_once(tmp_path, state, []) == 0
    assert _watch.check_once(tmp_path, state, []) == 0
    assert _watch.check_once(tmp_path, state, []) == 0

    assert calls == [tmp_path, tmp_path]
    assert '"last_reason": "version"' in state.read_text(encoding="utf-8")
