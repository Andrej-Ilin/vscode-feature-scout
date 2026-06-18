#!/usr/bin/env python
"""Run the VS Code feature scout when VS Code starts or its app version changes.

This script is meant to be called by a user LaunchAgent. It is deliberately
small and stateful: launchd wakes it via WatchPaths, then it checks whether
there is a new VS Code process identity or app version.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_REPO = Path(".")
DEFAULT_APP_PATHS = [
    Path("/Applications/Visual Studio Code.app"),
    Path.home() / "Applications" / "Visual Studio Code.app",
]
PROCESS_NAME = "Code"


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def find_code_pid() -> str | None:
    result = run_command(["pgrep", "-x", PROCESS_NAME])
    if result.returncode != 0:
        return None
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not pids:
        return None
    return sorted(pids, key=int)[0]


def process_started_at(pid: str) -> str:
    result = run_command(["ps", "-p", pid, "-o", "lstart="])
    if result.returncode != 0:
        return "unknown"
    return " ".join(result.stdout.split())


def vscode_version(app_paths: list[Path]) -> str:
    for app_path in app_paths:
        plist_path = app_path / "Contents" / "Info.plist"
        if not plist_path.exists():
            continue
        with plist_path.open("rb") as fh:
            plist = plistlib.load(fh)
        short_version = str(plist.get("CFBundleShortVersionString") or "")
        build_version = str(plist.get("CFBundleVersion") or "")
        if short_version and build_version:
            return f"{short_version} ({build_version})"
        if short_version or build_version:
            return short_version or build_version
    return "unknown"


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_process_event_id(*, pid: str, started_at: str, version: str) -> str:
    return f"{PROCESS_NAME}:{pid}:{started_at}:{version}"


def run_scout(repo: Path) -> int:
    result = subprocess.run([sys.executable, "-m", "vscode_feature_scout.cli"], cwd=repo, check=False)
    return result.returncode


def check_once(repo: Path, state_path: Path, app_paths: list[Path]) -> int:
    state = load_state(state_path)
    version = vscode_version(app_paths)
    pid = find_code_pid()

    process_event_id = ""
    if pid is not None:
        started_at = process_started_at(pid)
        process_event_id = build_process_event_id(pid=pid, started_at=started_at, version=version)
    else:
        started_at = ""

    version_changed = version != "unknown" and state.get("last_vscode_version") != version
    process_changed = bool(process_event_id) and state.get("last_process_event_id") != process_event_id

    if not version_changed and not process_changed:
        return 0

    reasons: list[str] = []
    if version_changed:
        reasons.append("version")
    if process_changed:
        reasons.append("process")

    scout_rc = run_scout(repo)
    payload = {
        "last_process_event_id": process_event_id or state.get("last_process_event_id", ""),
        "last_pid": pid or "",
        "last_process_started_at": started_at,
        "last_reason": ",".join(reasons),
        "last_scout_rc": str(scout_rc),
        "last_seen_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "last_vscode_version": version,
        "repo": str(repo),
    }
    save_state(state_path, payload)
    return scout_rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="Repo whose scout report should be written.")
    parser.add_argument("--state", type=Path, default=None, help="Watcher state path.")
    parser.add_argument(
        "--app",
        action="append",
        type=Path,
        default=None,
        help="VS Code .app path. Can be passed multiple times.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()
    state_path = args.state or repo / "outputs" / "vscode_feature_scout" / "launchd_state.json"
    app_paths = args.app or DEFAULT_APP_PATHS
    return check_once(repo, state_path, app_paths)


if __name__ == "__main__":
    raise SystemExit(main())
