from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any


GH_RETRY_ATTEMPTS = 4
GH_RETRY_DELAY_SECONDS = 1.5

APPROVER_TEAM_SLUGS = [
    "semconv-genai-approvers",
]


class TransientGhError(RuntimeError):
    pass


_RETRYABLE_GH_ERROR_FRAGMENTS = (
    "http 5",
    "gateway timeout",
    "timeout",
    "temporarily unavailable",
    "connection reset",
    "connection refused",
)


def is_retryable_gh_error(stderr: str) -> bool:
    text = stderr.lower()
    return any(fragment in text for fragment in _RETRYABLE_GH_ERROR_FRAGMENTS)


def sleep_for_retry(attempt: int) -> None:
    time.sleep(GH_RETRY_DELAY_SECONDS * (attempt + 1))


def run_gh(
    cmd: list[str],
    token: str | None = None,
    input_text: str | None = None,
    allowed_exit_codes: frozenset[int] | set[int] = frozenset({0}),
) -> str:
    env = {**os.environ, "GH_TOKEN": token} if token else None
    last_stderr = ""
    for attempt in range(GH_RETRY_ATTEMPTS):
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if proc.returncode in allowed_exit_codes:
            return proc.stdout
        last_stderr = proc.stderr.strip()
        if attempt == GH_RETRY_ATTEMPTS - 1 or not is_retryable_gh_error(last_stderr):
            break
        sleep_for_retry(attempt)
    message = f"{' '.join(cmd)} failed: {last_stderr}"
    if is_retryable_gh_error(last_stderr):
        raise TransientGhError(message)
    raise RuntimeError(message)


def run_gh_json(cmd: list[str], token: str | None = None, input_text: str | None = None) -> Any:
    return json.loads(run_gh(cmd, token=token, input_text=input_text) or "null")


def gh_api(path: str, paginate: bool = False, token: str | None = None) -> Any:
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json"]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    cmd.append(path)
    data = run_gh_json(cmd, token=token)
    if paginate and isinstance(data, list):
        flat: list[Any] = []
        for page in data:
            if isinstance(page, list):
                flat.extend(page)
            else:
                flat.append(page)
        return flat
    return data


def gh_graphql(query: str, fields: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for name, value in fields.items():
        if value is None:
            continue
        cmd.extend(["-F", f"{name}={value}"])
    return run_gh_json(cmd, token=token)


def gh_pr_view(repo: str, number: int) -> dict[str, Any]:
    fields = ",".join([
        "number", "title", "url", "author", "state", "isDraft",
        "mergeable", "mergeStateStatus", "createdAt", "updatedAt",
        "reviewDecision", "assignees",
    ])
    cmd = ["gh", "pr", "view", str(number), "--repo", repo, "--json", fields]
    last: dict[str, Any] = {}
    for attempt in range(GH_RETRY_ATTEMPTS):
        last = run_gh_json(cmd) or {}
        if last.get("mergeable") not in (None, "", "UNKNOWN"):
            return last
        if attempt < GH_RETRY_ATTEMPTS - 1:
            sleep_for_retry(attempt)
    return last


def gh_pr_checks(repo: str, number: int) -> list[dict[str, Any]] | None:
    cmd = [
        "gh", "pr", "checks", str(number), "--repo", repo, "--json",
        "name,state,bucket,workflow,description,link",
    ]
    for attempt in range(GH_RETRY_ATTEMPTS):
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        stdout = proc.stdout.strip()
        if proc.returncode == 8 and not stdout:
            return None
        if proc.returncode in (0, 1, 2, 8):
            if not stdout:
                return None
            try:
                checks = json.loads(stdout)
            except json.JSONDecodeError:
                return None
            return checks if isinstance(checks, list) else None
        stderr = proc.stderr.strip()
        if attempt == GH_RETRY_ATTEMPTS - 1 or not is_retryable_gh_error(stderr):
            return None
        sleep_for_retry(attempt)
    return None


def list_open_prs(repo: str) -> list[dict[str, Any]]:
    return run_gh_json([
        "gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "500",
        "--json", "number,title,author,isDraft,updatedAt,url",
    ])


def detect_repo() -> str:
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()


def load_reviewer_set(org: str) -> set[str]:
    token = os.environ.get("OTELBOT_TOKEN") or None
    reviewers: set[str] = set()
    for slug in APPROVER_TEAM_SLUGS:
        members = gh_api(
            f"/orgs/{org}/teams/{slug}/members?per_page=100",
            paginate=True,
            token=token,
        )
        reviewers.update(m["login"] for m in members)
    if not reviewers:
        raise RuntimeError(
            f"no reviewers found in teams {APPROVER_TEAM_SLUGS}; "
            f"the token must have org:read permission"
        )
    return {r.lower() for r in reviewers}


REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
            reviewThreads(first: 100, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    isOutdated
                    path
                    line
                    comments(first: 100) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        nodes {
                            id
                            body
                            createdAt
                            updatedAt
                            author {
                                login
                            }
                        }
                    }
                }
            }
        }
    }
}
"""

REVIEW_THREAD_COMMENTS_QUERY = """
query($thread_id: ID!, $after: String) {
    node(id: $thread_id) {
        ... on PullRequestReviewThread {
            comments(first: 100, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    body
                    createdAt
                    updatedAt
                    author {
                        login
                    }
                }
            }
        }
    }
}
"""


def fetch_remaining_review_thread_comments(thread_id: str, after: str | None) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    while after:
        data = gh_graphql(
            REVIEW_THREAD_COMMENTS_QUERY,
            {"thread_id": thread_id, "after": after},
        )
        connection = (((data.get("data") or {}).get("node") or {}).get("comments") or {})
        comments.extend(connection.get("nodes") or [])
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor") or ""
    return comments


def fetch_review_threads(owner: str, repo_name: str, number: int) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        data = gh_graphql(
            REVIEW_THREADS_QUERY,
            {"owner": owner, "name": repo_name, "number": number, "after": after},
        )
        page = (((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}).get("reviewThreads") or {}
        for thread in page.get("nodes") or []:
            comments = thread.get("comments") or {}
            page_info = comments.get("pageInfo") or {}
            if page_info.get("hasNextPage"):
                nodes = list(comments.get("nodes") or [])
                nodes.extend(fetch_remaining_review_thread_comments(
                    thread.get("id") or "",
                    page_info.get("endCursor") or "",
                ))
                comments["nodes"] = nodes
                comments["pageInfo"] = {"hasNextPage": False, "endCursor": ""}
                thread["comments"] = comments
            threads.append(thread)
        page_info = page.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return threads
        after = page_info.get("endCursor") or ""