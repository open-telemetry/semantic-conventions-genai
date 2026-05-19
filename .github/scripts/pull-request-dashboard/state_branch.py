#!/usr/bin/env python3
"""Manage the dashboard workflow's git-backed state branch."""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_MAX_ATTEMPTS = 3


@contextmanager
def temporary_state_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="pull-request-dashboard-") as temp_root:
        yield Path(temp_root) / "state"


def run(cmd: list[str], check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, cwd=cwd, text=True)


def remote_ref(state_branch: str) -> str:
    return f"refs/remotes/origin/{state_branch}"


def is_missing_remote_ref(stderr: str) -> bool:
    return "couldn't find remote ref" in stderr.lower()


def fetch_state_branch(state_branch: str, required: bool) -> bool:
    refspec = f"{state_branch}:{remote_ref(state_branch)}"
    proc = subprocess.run(
        ["git", "fetch", "origin", refspec],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return True
    if not required and is_missing_remote_ref(proc.stderr):
        return False
    message = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
    if required:
        raise RuntimeError(f"failed to fetch required state branch {state_branch}: {message}")
    raise RuntimeError(f"failed to fetch optional state branch {state_branch}: {message}")


def has_state_branch(state_branch: str) -> bool:
    proc = run(["git", "show-ref", "--verify", "--quiet", remote_ref(state_branch)], check=False)
    return proc.returncode == 0


def remove_existing_state_dir(state_dir: Path) -> None:
    if not state_dir.exists():
        return
    run(["git", "worktree", "remove", "--force", str(state_dir)], check=False)
    if not state_dir.exists():
        return
    if state_dir.is_dir():
        shutil.rmtree(state_dir)
    else:
        state_dir.unlink()


def checkout_state(state_dir: Path, state_branch: str, require_existing: bool) -> None:
    remove_existing_state_dir(state_dir)
    fetch_state_branch(state_branch, required=require_existing)
    if has_state_branch(state_branch):
        run(["git", "worktree", "add", "-B", state_branch, str(state_dir), f"origin/{state_branch}"])
        return
    run(["git", "worktree", "add", "--detach", str(state_dir), "HEAD"])
    run(["git", "switch", "--orphan", state_branch], cwd=state_dir)
    run(["git", "rm", "-rf", "."], cwd=state_dir, check=False)


def reset_state(state_dir: Path, state_branch: str) -> bool:
    if not fetch_state_branch(state_branch, required=False):
        return False
    run(["git", "reset", "--hard", f"origin/{state_branch}"], cwd=state_dir)
    return True


def push_state(state_dir: Path, state_branch: str) -> bool:
    cmd = ["git"]
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        cmd.extend(["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credential}"])
    cmd.extend(["push", "--force-with-lease", "origin", state_branch])
    return run(cmd, cwd=state_dir, check=False).returncode == 0


def configure_git() -> None:
    run(["git", "config", "user.email", "otelbot@users.noreply.github.com"])
    run(["git", "config", "user.name", "otelbot"])


def copy_snapshots(snapshots: list[tuple[Path, Path]]) -> None:
    for source, destination in snapshots:
        if source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def push_state_changes(
    state_dir: Path,
    commit_message: str,
    update_state: Callable[[], int],
    *,
    state_branch: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    add_paths: list[str] | None = None,
    retry_snapshots: list[tuple[Path, Path]] | None = None,
) -> int:
    configure_git()
    checkout_state(state_dir, state_branch, require_existing=False)
    paths_to_add = add_paths or ["."]
    snapshots = retry_snapshots or []

    for attempt in range(1, max_attempts + 1):
        status = update_state()
        if status != 0:
            return status

        run(["git", "add", "--", *paths_to_add], cwd=state_dir)
        if run(["git", "diff", "--cached", "--quiet"], cwd=state_dir, check=False).returncode == 0:
            print("no state changes to push", file=sys.stderr)
            return 0

        run(["git", "commit", "-m", commit_message], cwd=state_dir)
        copy_snapshots(snapshots)

        if push_state(state_dir, state_branch):
            print(f"state pushed on attempt {attempt}", file=sys.stderr)
            return 0

        if attempt >= max_attempts:
            print(f"CAS retry exhausted after {attempt} attempt(s)", file=sys.stderr)
            return 1

        print(f"push rejected (attempt {attempt}); refetching and retrying", file=sys.stderr)
        if not reset_state(state_dir, state_branch):
            return 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    checkout = subparsers.add_parser("checkout", help="check out the accepted state branch")
    checkout.add_argument("--state-branch", required=True)
    checkout.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "checkout":
        configure_git()
        checkout_state(args.state_dir, args.state_branch, require_existing=True)
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())