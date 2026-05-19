#!/usr/bin/env python3
"""Publish the accepted PR dashboard markdown to the dashboard issue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

from github_cli import detect_repo, gh_api, run_gh
from state import dashboard_markdown_path, set_state_dir
import state_branch


DASHBOARD_TITLE = "Pull Request Dashboard"
DASHBOARD_LABEL = "dashboard"


def find_dashboard_issue(repo: str) -> int | None:
    label = quote(DASHBOARD_LABEL, safe="")
    issues = gh_api(f"/repos/{repo}/issues?state=open&labels={label}&per_page=100", paginate=True)
    numbers = sorted(
        issue["number"]
        for issue in issues
        if isinstance(issue, dict)
        and issue.get("pull_request") is None
        and issue.get("title") == DASHBOARD_TITLE
        and isinstance(issue.get("number"), int)
    )
    return numbers[0] if numbers else None


def publish_dashboard(repo: str, dashboard_body: Path) -> None:
    if not dashboard_body.exists():
        raise RuntimeError(f"dashboard markdown not found: {dashboard_body}")

    number = find_dashboard_issue(repo)
    if number is not None:
        print(f"publishing dashboard issue #{number}", file=sys.stderr)
        run_gh([
            "gh",
            "issue",
            "edit",
            str(number),
            "--repo",
            repo,
            "--body-file",
            str(dashboard_body),
        ])
        return

    print("creating dashboard issue", file=sys.stderr)
    run_gh([
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        DASHBOARD_TITLE,
        "--label",
        DASHBOARD_LABEL,
        "--body-file",
        str(dashboard_body),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-branch",
        required=True,
        help="git branch used for workflow state",
    )
    args = parser.parse_args()

    repo = detect_repo()
    with state_branch.temporary_state_dir() as state_dir:
        set_state_dir(state_dir)
        state_branch.configure_git()
        state_branch.checkout_state(state_dir, args.state_branch, require_existing=True)
        publish_dashboard(repo, dashboard_markdown_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
