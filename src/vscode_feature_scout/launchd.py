#!/usr/bin/env python
"""Install or remove the global macOS LaunchAgent for VS Code feature scouting."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = Path(".")
DEFAULT_LABEL = "dev.vscode-feature-scout"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs"
DEFAULT_VSCODE_APP_PATHS = [
    Path("/Applications/Visual Studio Code.app"),
    Path.home() / "Applications" / "Visual Studio Code.app",
]
DEFAULT_VSCODE_LOGS_DIR = Path.home() / "Library" / "Application Support" / "Code" / "logs"


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def plist_path(label: str) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label}.plist"


def default_watch_paths() -> list[Path]:
    paths = [DEFAULT_VSCODE_LOGS_DIR]
    paths.extend(app_path / "Contents" / "Info.plist" for app_path in DEFAULT_VSCODE_APP_PATHS)
    return paths


def build_plist(*, label: str, repo: Path, poll_interval: int, watch_paths: list[Path]) -> dict:
    path_env = os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin")
    payload = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "vscode_feature_scout.watch",
            "--repo",
            str(repo),
        ],
        "WorkingDirectory": str(repo),
        "RunAtLoad": True,
        "WatchPaths": [str(path) for path in watch_paths],
        "StandardOutPath": str(LOG_DIR / f"{label}.out.log"),
        "StandardErrorPath": str(LOG_DIR / f"{label}.err.log"),
        "EnvironmentVariables": {
            "PATH": path_env,
        },
    }
    if poll_interval > 0:
        payload["StartInterval"] = poll_interval
    return payload


def write_plist(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        plistlib.dump(payload, fh, sort_keys=True)


def run_launchctl(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], check=check, capture_output=True, text=True)


def bootout(label: str, path: Path) -> None:
    domain = launchctl_domain()
    run_launchctl(["bootout", domain, str(path)], check=False)
    run_launchctl(["bootout", f"{domain}/{label}"], check=False)


def bootstrap(label: str, path: Path) -> None:
    domain = launchctl_domain()
    result = run_launchctl(["bootstrap", domain, str(path)], check=False)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "launchctl bootstrap failed")
    run_launchctl(["enable", f"{domain}/{label}"], check=False)


def print_status(label: str) -> int:
    result = run_launchctl(["print", f"{launchctl_domain()}/{label}"], check=False)
    if result.returncode == 0:
        print(result.stdout.rstrip())
        return 0
    print(result.stderr.rstrip() or result.stdout.rstrip() or f"{label} is not loaded")
    return result.returncode


def install(*, label: str, repo: Path, poll_interval: int, load: bool, watch_paths: list[Path]) -> Path:
    repo = repo.resolve()
    path = plist_path(label)
    payload = build_plist(
        label=label,
        repo=repo,
        poll_interval=poll_interval,
        watch_paths=watch_paths,
    )
    write_plist(path, payload)
    print(f"Wrote {path}")
    if load:
        bootout(label, path)
        bootstrap(label, path)
        print(f"Loaded {label}")
    return path


def uninstall(*, label: str, keep_plist: bool) -> None:
    path = plist_path(label)
    bootout(label, path)
    if path.exists() and not keep_plist:
        path.unlink()
        print(f"Removed {path}")
    else:
        print(f"Unloaded {label}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--install", action="store_true", help="Write the LaunchAgent plist.")
    actions.add_argument("--uninstall", action="store_true", help="Unload and remove the LaunchAgent plist.")
    actions.add_argument("--status", action="store_true", help="Print launchctl status for the LaunchAgent.")
    parser.add_argument("--load", action="store_true", help="Load/reload the LaunchAgent after --install.")
    parser.add_argument("--keep-plist", action="store_true", help="With --uninstall, unload but keep the plist file.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="Repo path to scout.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="LaunchAgent label.")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=0,
        help="Optional fallback polling interval in seconds. Default 0 disables polling.",
    )
    parser.add_argument(
        "--watch-path",
        action="append",
        type=Path,
        default=None,
        help="Additional path for launchd WatchPaths. Can be passed multiple times.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.install:
        watch_paths = args.watch_path or default_watch_paths()
        install(
            label=args.label,
            repo=args.repo,
            poll_interval=args.poll_interval,
            load=args.load,
            watch_paths=watch_paths,
        )
        return 0
    if args.uninstall:
        uninstall(label=args.label, keep_plist=args.keep_plist)
        return 0
    return print_status(args.label)


if __name__ == "__main__":
    raise SystemExit(main())
