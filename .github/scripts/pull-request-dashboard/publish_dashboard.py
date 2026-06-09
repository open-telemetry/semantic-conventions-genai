#!/usr/bin/env python3
"""Publish the accepted PR dashboard markdown to the dashboard issue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from github_cli import detect_repo, gh_graphql, run_gh
from state import dashboard_markdown_path, set_state_dir
import state_branch


DASHBOARD_TITLE = "Pull Request Dashboard"
DASHBOARD_LABEL = "dashboard"


# GraphQL is used instead of the REST `/repos/{repo}/issues` list endpoint
# because that endpoint has been observed to sometimes omit the existing
# open, `dashboard`-labeled issue from its results (across every sort, page
# size, and `since` variant), even though `GET /repos/{repo}/issues/<n>` and
# the GraphQL `repository.issues` connection both still return it. When that
# happens via REST, this script would create a duplicate dashboard issue
# instead of updating the existing one.
_FIND_DASHBOARD_ISSUE_QUERY = """
query ($owner: String!, $name: String!, $label: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100
      after: $after
      states: OPEN
      filterBy: { labels: [$label] }
      orderBy: { field: CREATED_AT, direction: ASC }
    ) {
      pageInfo { hasNextPage endCursor }
      nodes { number title }
    }
  }
}
"""


def find_dashboard_issue(repo: str) -> int | None:
    owner, _, name = repo.partition("/")
    after: str | None = None
    while True:
        data = gh_graphql(
            _FIND_DASHBOARD_ISSUE_QUERY,
            {"owner": owner, "name": name, "label": DASHBOARD_LABEL, "after": after},
        )
        connection = data["data"]["repository"]["issues"]
        for node in connection["nodes"]:
            if node["title"] == DASHBOARD_TITLE:
                return node["number"]
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            return None
        after = page_info["endCursor"]


def dashboard_issue_url(repo: str) -> str:
    number = find_dashboard_issue(repo)
    if number is None:
        raise RuntimeError(f"dashboard issue not found in {repo}")
    return f"https://github.com/{repo}/issues/{number}"


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
        "--print-dashboard-url",
        action="store_true",
        help="print the existing dashboard issue URL and exit",
    )
    parser.add_argument(
        "--state-branch",
        help="git branch used for workflow state",
    )
    args = parser.parse_args()

    repo = detect_repo()
    if args.print_dashboard_url:
        print(dashboard_issue_url(repo))
        return 0

    if not args.state_branch:
        parser.error("--state-branch is required unless --print-dashboard-url is set")

    with state_branch.temporary_state_dir() as state_dir:
        set_state_dir(state_dir)
        state_branch.configure_git()
        state_branch.checkout_state(state_dir, args.state_branch, require_existing=True)
        publish_dashboard(repo, dashboard_markdown_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
