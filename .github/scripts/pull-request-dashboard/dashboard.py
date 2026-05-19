#!/usr/bin/env python3
"""Generate a deterministic pull request dashboard with thread-level LLM triage.

The script keeps repository facts deterministic and asks the LLM only one
narrow question per unresolved discussion thread: who has the next action for
that thread?

The workflow publishes the rendered markdown from the accepted state branch.
This script checks out that branch, commits changed dashboard state files, and
pushes with `git push --force-with-lease` so concurrent runs use git refs as
the durable compare-and-swap boundary.

Usage:
    python .github/scripts/pull-request-dashboard/dashboard.py --state-branch BRANCH
                                                               [--pr-number N]
                                                               [--model NAME]

Architecture overview
---------------------

Workflow state that survives across runs lives on the state branch:

  dashboard-state.json     cached per-PR routing results
  notification-state.json  per-PR Slack history
    pull-request-dashboard.md rendered dashboard body

The dashboard issue body is rendered fresh each run; no state markers are
embedded in it.

A run flows like this:

  list_open_prs
       v
  compute_pr_results
       single-PR + cache hit:  reuse cached results, recompute only the trigger PR
       otherwise:              rebuild all PRs in parallel
       v
  reconcile_with_latest_dashboard
       reload dashboard-state in case a concurrent run updated it
       v
  render_dashboard_body                (write pull-request-dashboard.md)
       v
  save_dashboard_state_cache

Slack notifications are sent by notify_slack.py in a separate serialized
workflow job. That job loads the latest accepted dashboard state and
notification state, sends any due notifications, and pushes the updated
notification state with the same git CAS pattern.

State files are committed and pushed first. Only after that state branch push
succeeds does a follow-up publishing job fetch the accepted rendered dashboard
body from the state branch and publish it to the dashboard issue.

Full (no --pr-number) runs always rebuild every PR and write unconditionally.
Single-PR runs are optimistic-concurrency updates of just one PR slot in the
cached state.

Field schemas
-------------

Two record shapes flow through the pipeline as ``dict[str, Any]``. They are
built up across stages, so not every field is present at every point.

``result`` (one per PR) — produced by ``build_pr_result``:

  pr_number             int            PR number.
  pr_title              str            PR title.
  pr_url                str            PR URL.
  failed                bool           True on any failure; False on success.
  route                  str            Routing bucket: one of ROUTE_ORDER
                                       ("maintainer", "approver", "author",
                                       "external", "transient-failure",
                                       "unknown").
  facts                 dict           See below. Empty on data-fetch/build
                                       failures; classification failures may
                                       keep deterministic facts for rendering.
  threads               list[dict]     Unresolved discussion threads. Internal.
  classifications       list[dict]     Per-thread LLM decisions. Internal.
  error                 str            Error detail, set only on failure paths.

Only ``pr_number``, ``pr_url``, ``failed``, ``route``, and ``facts``
survive into the cached dashboard state (see ``stored_result``).

``facts`` (one per PR) — built in two stages:

  Stage 1 — compute_facts (deterministic from GitHub data):
    author                          str           Effective author (human, after
                                                  bot-delegation resolution).
    assignees                       list[str]     PR assignees.
    is_otelbot_author               bool          PR opened by app/otelbot.
    is_draft                        bool
    approved                        bool          reviewDecision == APPROVED.
    ci_failing_count                int           Absent when checks could not
                                                  be fetched.
    ci_pending_count                int           Absent when checks could not
                                                  be fetched.
    conflicts                       str           "yes" | "no" | "unknown".
    created_at                      str (iso)
    last_activity_at                str (iso)
    last_author_activity_at         str (iso)
    last_approver_activity_at       str (iso)
    last_external_activity_at       str (iso)

  Stage 2 — add_wait_age_facts (depends on routing + threads):
    waiting_since                   str (iso)     Oldest pending thread, or
                                                  route-appropriate fallback,
                                                  or PR creation time.
    waiting_age_basis               str           Which heuristic chose
                                                  waiting_since.

Stage-2 fields are absent on failure paths (failed is True). Human-readable
``age`` strings (e.g. ``3h``) are derived at render time from these
timestamps rather than persisted, so the cached JSON stays stable across
runs when no underlying PR data has changed.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from github_cli import (
    TransientGhError,
    detect_repo,
    fetch_review_threads,
    gh_api,
    gh_pr_checks,
    gh_pr_view,
    list_open_prs,
    load_reviewer_set,
)
from classification import (
    THREAD_RECENT_COMMENTS_LIMIT,
    classify_threads,
    is_conflict_resolution_comment,
    normalize_thread_action,
    prune_classification_cache,
)
from render import render_pr_tables
from state import (
    dashboard_markdown_path,
    dashboard_state_from_results,
    empty_state,
    load_dashboard_state_cache,
    results_from_dashboard_state,
    save_dashboard_state_cache,
    set_state_dir,
    stored_result,
    update_dashboard_state_for_pr,
)
import state_branch
from utils import actor_login, format_ts, parse_ts, truncate

# --- CLI defaults ----------------------------------------------------------
# Parallel PRs processed at once (each PR's threads are classified
# sequentially within that worker).
DEFAULT_JOBS = 4
DEFAULT_MODEL = "gpt-5.4-mini"

# ---------------------------------------------------------------- model helpers


def role_for(login: str, author: str, reviewers: set[str]) -> str:
    if not login:
        return "outsider"
    low = login.lower()
    if low == author.lower():
        return "author"
    if low in reviewers:
        return "approver"
    if low.startswith("app/") or low.endswith("[bot]"):
        return "bot"
    return "outsider"


# Bot logins appear in two shapes depending on the API:
#   - `gh pr view`'s `author` field uses the `app/<slug>` form (e.g.
#     `app/copilot-swe-agent`), which is what `_DELEGATING_BOT_AUTHORS`
#     matches against in `effective_author`.
#   - The Pulls/commits endpoint's `committer.login` field returns the bare
#     slug (e.g. `copilot`), which is what `_BOT_COMMITTER_LOGINS` matches
#     against in `detect_human_delegator`.
# Both sets contain `copilot` because the slug shows up in both contexts.
_BOT_COMMITTER_LOGINS = {"copilot"}
_DELEGATING_BOT_AUTHORS = {"app/copilot-swe-agent", "copilot"}


def is_bot_login(login: str) -> bool:
    if not login:
        return True
    low = login.lower()
    if low in _BOT_COMMITTER_LOGINS:
        return True
    return low.startswith("app/") or low.endswith("[bot]")


def detect_human_delegator(commits: list[dict[str, Any]]) -> str:
    if not commits:
        return ""
    login = actor_login(commits[0].get("committer") or {})
    return "" if is_bot_login(login) else login


def fetch_pr_raw(
    repo: str,
    owner: str,
    repo_name: str,
    pr_summary: dict[str, Any],
) -> dict[str, Any]:
    number = pr_summary["number"]
    with ThreadPoolExecutor() as pool:
        f_pr = pool.submit(gh_pr_view, repo, number)
        f_issue = pool.submit(
            gh_api,
            f"/repos/{owner}/{repo_name}/issues/{number}/comments?per_page=100",
            True,
        )
        f_revcom = pool.submit(
            gh_api,
            f"/repos/{owner}/{repo_name}/pulls/{number}/comments?per_page=100",
            True,
        )
        f_reviews = pool.submit(
            gh_api,
            f"/repos/{owner}/{repo_name}/pulls/{number}/reviews?per_page=100",
            True,
        )
        f_commits = pool.submit(
            gh_api,
            f"/repos/{owner}/{repo_name}/pulls/{number}/commits?per_page=100",
            True,
        )
        f_checks = pool.submit(gh_pr_checks, repo, number)
        f_threads = pool.submit(fetch_review_threads, owner, repo_name, number)
        return {
            "summary": pr_summary,
            "pr": f_pr.result(),
            "issue_comments": f_issue.result() or [],
            "review_comments": f_revcom.result() or [],
            "reviews": f_reviews.result() or [],
            "commits": f_commits.result() or [],
            "checks": f_checks.result(),
            "review_threads": f_threads.result() or [],
        }


def effective_author(raw: dict[str, Any]) -> str:
    pr = raw["pr"]
    summary = raw["summary"]
    author = actor_login(pr.get("author") or {}) or actor_login(summary.get("author") or {})
    if author.lower() in _DELEGATING_BOT_AUTHORS:
        delegator = detect_human_delegator(raw["commits"])
        if delegator:
            return delegator
    return author


def is_merge_commit(commit: dict[str, Any]) -> bool:
    return len(commit.get("parents") or []) >= 2


def normalize_events(raw: dict[str, Any], author: str, reviewers: set[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for c in raw["commits"]:
        commit_obj = c.get("commit") or {}
        commit_author = commit_obj.get("author") or {}
        login = actor_login(c.get("author") or {}) or commit_author.get("name") or ""
        sha = c.get("sha") or ""
        events.append({
            "kind": "commit",
            "timestamp": commit_author.get("date") or "",
            "actor": login,
            "actor_role": role_for(login, author, reviewers),
            "body": commit_obj.get("message") or "",
            "state": None,
            "path": None,
            "sha": sha[:7],
            "is_merge_from_base_by_non_author": is_merge_commit(c) and login.lower() != author.lower(),
        })
    for c in raw["issue_comments"]:
        login = actor_login(c.get("user") or {})
        events.append({
            "kind": "issue-comment",
            "timestamp": c.get("updated_at") or c.get("created_at") or "",
            "actor": login,
            "actor_role": role_for(login, author, reviewers),
            "body": c.get("body") or "",
            "state": None,
            "path": None,
            "sha": None,
            "is_merge_from_base_by_non_author": False,
        })
    for c in raw["review_comments"]:
        login = actor_login(c.get("user") or {})
        events.append({
            "kind": "review-comment",
            "timestamp": c.get("updated_at") or c.get("created_at") or "",
            "actor": login,
            "actor_role": role_for(login, author, reviewers),
            "body": c.get("body") or "",
            "state": None,
            "path": c.get("path"),
            "sha": None,
            "is_merge_from_base_by_non_author": False,
        })
    for r in raw["reviews"]:
        login = actor_login(r.get("user") or {})
        state = r.get("state") or ""
        events.append({
            "kind": "review-state",
            "timestamp": r.get("submitted_at") or "",
            "actor": login,
            "actor_role": role_for(login, author, reviewers),
            "body": r.get("body") or "",
            "state": state,
            "path": None,
            "sha": None,
            "is_merge_from_base_by_non_author": False,
        })
    events = [e for e in events if e["timestamp"]]
    events.sort(key=lambda e: e["timestamp"])
    return events


def is_substantive_activity(event: dict[str, Any]) -> bool:
    if event.get("is_merge_from_base_by_non_author"):
        return False
    # Bot events never count as substantive: merge-bot pings, CI status
    # comments, and the like must not refresh the waiting clock. Bot PR
    # authors are remapped to their human delegator in `effective_author`,
    # so a real human's activity still shows up here under that login.
    if event.get("actor_role") == "bot":
        return False
    if event["kind"] == "review-state" and event.get("state") != "COMMENTED":
        return True
    return bool((event.get("body") or "").strip())


def compute_conflicts(pr: dict[str, Any]) -> str:
    merge_state = pr.get("mergeStateStatus")
    mergeable = pr.get("mergeable")
    if mergeable == "CONFLICTING" or merge_state == "DIRTY":
        return "yes"
    if mergeable in (None, "", "UNKNOWN"):
        return "unknown"
    return "no"


def latest_substantive_activity(events: list[dict[str, Any]], actor_roles: set[str]) -> datetime | None:
    timestamps = [
        parse_ts(e["timestamp"])
        for e in events
        if e.get("actor_role") in actor_roles and is_substantive_activity(e)
    ]
    timestamps = [ts for ts in timestamps if ts is not None]
    return max(timestamps) if timestamps else None


def compute_facts(raw: dict[str, Any], author: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    pr = raw["pr"]
    checks = raw["checks"]
    failing = [c for c in checks or [] if (c.get("state") or "").upper() in ("FAILURE", "ERROR")]
    pending = [c for c in checks or [] if (c.get("state") or "").upper() in ("PENDING", "QUEUED", "IN_PROGRESS")]
    last_activity_ts = parse_ts(pr["updatedAt"])
    created_ts = parse_ts(pr["createdAt"])
    author_activity_ts = latest_substantive_activity(events, {"author"})
    approver_activity_ts = latest_substantive_activity(events, {"approver"})
    external_activity_ts = latest_substantive_activity(events, {"outsider"})
    api_author = actor_login(pr.get("author") or {})
    assignees = [actor_login(a) for a in (pr.get("assignees") or [])]
    assignees = [a for a in assignees if a]
    facts = {
        "author": author,
        "assignees": assignees,
        "is_otelbot_author": api_author.lower() == "app/otelbot",
        "is_draft": bool(pr.get("isDraft")),
        "approved": pr.get("reviewDecision") == "APPROVED",
        "conflicts": compute_conflicts(pr),
        "created_at": format_ts(created_ts),
        "last_activity_at": format_ts(last_activity_ts),
        "last_author_activity_at": format_ts(author_activity_ts),
        "last_approver_activity_at": format_ts(approver_activity_ts),
        "last_external_activity_at": format_ts(external_activity_ts),
    }
    if checks is not None:
        facts["ci_failing_count"] = len(failing)
        facts["ci_pending_count"] = len(pending)
    return facts


def thread_comment(timestamp: str, actor: str, author: str, reviewers: set[str], body: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "actor": actor,
        "actor_role": role_for(actor, author, reviewers),
        "body": truncate(body),
    }


def add_thread_facts(
    thread: dict[str, Any],
    comments: list[dict[str, Any]],
    facts: dict[str, Any],
) -> dict[str, Any]:
    thread["thread_facts"] = {
        "latest_comment_role": comments[-1].get("actor_role"),
        "current_conflicts": facts.get("conflicts"),
    }
    return thread


def group_review_threads(
    raw: dict[str, Any],
    author: str,
    reviewers: set[str],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    for thread in raw["review_threads"]:
        if thread.get("isResolved") or thread.get("isOutdated"):
            continue
        comments = []
        for c in ((thread.get("comments") or {}).get("nodes") or []):
            actor = actor_login(c.get("author") or {})
            comments.append(thread_comment(
                c.get("updatedAt") or c.get("createdAt") or "",
                actor,
                author,
                reviewers,
                c.get("body") or "",
            ))
        comments = [c for c in comments if c["timestamp"]]
        comments.sort(key=lambda c: c["timestamp"])
        if not comments:
            continue
        threads.append(add_thread_facts({
            "thread_id": thread.get("id") or f"review-thread-{len(threads) + 1}",
            "thread_kind": "review-comment-thread",
            "path": thread.get("path"),
            "line": thread.get("line"),
            "resolved": False,
            "comments": comments,
        }, comments, facts))
    threads.sort(key=lambda t: t["comments"][-1]["timestamp"])
    return threads


def latest_approver_review_event(events: list[dict[str, Any]]) -> str | None:
    timestamps = [
        e["timestamp"]
        for e in events
        if e.get("actor_role") == "approver"
        and e["kind"] in ("review-comment", "review-state")
        and is_substantive_activity(e)
    ]
    return max(timestamps) if timestamps else None


def group_pr_conversation(
    raw: dict[str, Any],
    events: list[dict[str, Any]],
    review_threads: list[dict[str, Any]],
    author: str,
    reviewers: set[str],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    comments = []
    for c in raw["issue_comments"]:
        actor = actor_login(c.get("user") or {})
        comment = thread_comment(c.get("updated_at") or c.get("created_at") or "", actor, author, reviewers, c.get("body") or "")
        if comment["timestamp"] and comment["actor_role"] != "bot" and comment["body"]:
            comments.append(comment)
    comments.sort(key=lambda c: c["timestamp"])
    if not comments:
        return []

    latest_review_ts = latest_approver_review_event(events)
    if latest_review_ts:
        selected = [c for c in comments if c["timestamp"] > latest_review_ts]
        if not selected and review_threads:
            return []
    elif review_threads:
        selected = []
    else:
        selected = comments

    if facts.get("conflicts") == "no":
        selected = [c for c in selected if not is_conflict_resolution_comment(c.get("body") or "")]
    selected = selected[-THREAD_RECENT_COMMENTS_LIMIT:]
    if not selected:
        return []
    return [add_thread_facts({
        "thread_id": "pr-conversation",
        "thread_kind": "pr-conversation",
        "path": None,
        "line": None,
        "resolved": False,
        "comments": selected,
    }, selected, facts)]


def group_discussion_threads(
    raw: dict[str, Any],
    events: list[dict[str, Any]],
    author: str,
    reviewers: set[str],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    review_threads = group_review_threads(raw, author, reviewers, facts)
    return review_threads + group_pr_conversation(raw, events, review_threads, author, reviewers, facts)


# ---------------------------------------------------------------- routing


ROUTE_THREAD_ACTIONS = {
    "author": "author",
    "approver": "reviewer",
    "maintainer": "reviewer",
    "external": "external",
}


def action_counts(classifications: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"author": 0, "reviewer": 0, "external": 0, "none": 0, "unclear": 0}
    for c in classifications:
        action = normalize_thread_action((c.get("decision") or {}).get("thread_action") or "")
        counts[action] += 1
    return counts


def route_pr(facts: dict[str, Any], classifications: list[dict[str, Any]]) -> str:
    counts = action_counts(classifications)
    # Precedence:
    #   1. otelbot PRs are always either "external" (if any thread points
    #      outside the repo) or "approver" — they have no human author to
    #      route to.
    #   2. Any single thread waiting on the author -> "author".
    #   3. Otherwise any thread waiting on something external -> "external".
    #   4. Otherwise the PR's approval status decides: approved -> ready for
    #      a maintainer to merge; not approved -> still waiting on approvers
    #      (whether or not a thread is currently pending on a reviewer).
    if facts.get("is_otelbot_author"):
        return "external" if counts["external"] else "approver"
    if counts["author"]:
        return "author"
    if counts["external"]:
        return "external"
    if facts.get("approved"):
        return "maintainer"
    return "approver"


def threads_by_id(threads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {t["thread_id"]: t for t in threads}


def thread_latest_comment_ts(thread: dict[str, Any] | None) -> datetime | None:
    comments = (thread or {}).get("comments") or []
    if not comments:
        return None
    return parse_ts(comments[-1].get("timestamp") or "")


def oldest_thread_wait_ts(
    threads: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    action: str,
) -> datetime | None:
    by_id = threads_by_id(threads)
    timestamps = [
        thread_latest_comment_ts(by_id.get(c.get("thread_id") or ""))
        for c in classifications
        if normalize_thread_action((c.get("decision") or {}).get("thread_action") or "") == action
    ]
    timestamps = [ts for ts in timestamps if ts is not None]
    return min(timestamps) if timestamps else None


def fallback_wait_ts(route: str, facts: dict[str, Any]) -> tuple[datetime | None, str]:
    if route in ("approver", "maintainer"):
        return parse_ts(facts.get("last_author_activity_at") or ""), "last_author_activity"
    if route == "author":
        return parse_ts(facts.get("last_approver_activity_at") or ""), "last_approver_activity"
    if route == "external":
        return parse_ts(facts.get("last_external_activity_at") or ""), "last_external_activity"
    return parse_ts(facts.get("last_activity_at") or ""), "last_activity"


def add_wait_age_facts(
    facts: dict[str, Any],
    route: str,
    threads: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
) -> None:
    action = ROUTE_THREAD_ACTIONS.get(route)
    wait_ts = oldest_thread_wait_ts(threads, classifications, action) if action else None
    basis = "oldest_pending_thread" if wait_ts else ""
    if wait_ts is None:
        wait_ts, basis = fallback_wait_ts(route, facts)
    if wait_ts is None:
        wait_ts = parse_ts(facts.get("created_at") or "")
        basis = "created"
    facts["waiting_since"] = format_ts(wait_ts)
    facts["waiting_age_basis"] = basis


# ---------------------------------------------------------------- main


def build_pr_result(
    repo: str,
    owner: str,
    repo_name: str,
    pr_summary: dict[str, Any],
    reviewers: set[str],
    model: str,
) -> dict[str, Any] | None:
    number = pr_summary["number"]
    try:
        raw = fetch_pr_raw(repo, owner, repo_name, pr_summary)
        if raw["pr"].get("state") != "OPEN" or raw["pr"].get("isDraft"):
            return None
        author = effective_author(raw)
        events = normalize_events(raw, author, reviewers)
        facts = compute_facts(raw, author, events)
        threads = group_discussion_threads(raw, events, author, reviewers, facts)
        classifications = classify_threads(number, threads, model)
        failed_classifications = [c for c in classifications if c.get("failed")]
        if failed_classifications:
            return {
                "pr_number": number,
                "pr_title": raw["pr"].get("title") or "",
                "pr_url": raw["pr"].get("url") or "",
                "failed": True,
                "facts": facts,
                "threads": threads,
                "classifications": classifications,
                "route": "unknown",
                "error": f"{len(failed_classifications)} thread classification(s) failed",
            }
        route = route_pr(facts, classifications)
        add_wait_age_facts(facts, route, threads, classifications)
        return {
            "pr_number": number,
            "pr_title": raw["pr"].get("title") or "",
            "pr_url": raw["pr"].get("url") or "",
            "failed": False,
            "facts": facts,
            "threads": threads,
            "classifications": classifications,
            "route": route,
        }
    except TransientGhError as e:
        return {
            "pr_number": number,
            "failed": True,
            "facts": {},
            "threads": [],
            "classifications": [],
            "route": "transient-failure",
            "error": repr(e),
        }
    except Exception as e:
        # Boundary: one bad PR must not break the dashboard run. Log the
        # traceback so genuine bugs are visible in workflow logs instead
        # of being silently routed to "Unknown" forever.
        print(f"  warning: PR #{number} failed to build result:", file=sys.stderr)
        traceback.print_exc()
        return {
            "pr_number": number,
            "failed": True,
            "facts": {},
            "threads": [],
            "classifications": [],
            "route": "unknown",
            "error": repr(e),
        }


@dataclass
class DashboardCalculation:
    results: dict[int, dict[str, Any]]
    dashboard_state: dict[str, Any]
    trigger_pr_result: dict[str, Any] | None = None
    current_pr_result: dict[str, Any] | None = None
    starting_pr_result: dict[str, Any] | None = None
    used_cached_dashboard_state: bool = False


def compute_pr_results(
    repo: str,
    owner: str,
    repo_name: str,
    non_drafts: list[dict[str, Any]],
    open_pr_numbers: set[int],
    reviewers: set[str],
    pr_number: int | None,
    jobs: int,
    model: str,
) -> DashboardCalculation:
    dashboard_state = empty_state()
    if pr_number:
        dashboard_state = load_dashboard_state_cache()

    if pr_number and dashboard_state.get("_loaded_from_dashboard"):
        print(f"refreshing dashboard state for PR #{pr_number}", file=sys.stderr)
        results = results_from_dashboard_state(dashboard_state, open_pr_numbers)
        starting_pr_result = results.get(pr_number)
        trigger_pr_result = build_pr_result(repo, owner, repo_name, {"number": pr_number}, reviewers, model)
        if trigger_pr_result is None:
            results.pop(pr_number, None)
        else:
            results[pr_number] = trigger_pr_result
        current_pr_result = stored_result(trigger_pr_result) if trigger_pr_result is not None else None
        return DashboardCalculation(
            results=results,
            dashboard_state=dashboard_state,
            trigger_pr_result=trigger_pr_result,
            current_pr_result=current_pr_result,
            starting_pr_result=starting_pr_result,
            used_cached_dashboard_state=True,
        )

    if pr_number:
        print("dashboard result state not found; rebuilding all PRs", file=sys.stderr)
    print(f"processing {len(non_drafts)} PR(s) in {repo} (model={model}, jobs={jobs})", file=sys.stderr)
    results = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(build_pr_result, repo, owner, repo_name, pr, reviewers, model): pr
            for pr in non_drafts
        }
        for i, fut in enumerate(as_completed(futures), 1):
            pr = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                # Boundary: `build_pr_result` already catches its own
                # exceptions, so this is a safety net for cancellations or
                # bugs that escape the inner handler. One bad future must
                # not break the whole dashboard run.
                res = {"pr_number": pr["number"], "failed": True, "route": "unknown", "error": repr(e)}
            if res is None:
                # PR was closed or converted to draft between list_open_prs
                # and the worker run; skip it.
                continue
            results[pr["number"]] = res
            counts = action_counts(res.get("classifications") or [])
            print(
                f"  [{i}/{len(non_drafts)}] #{pr['number']} -> {res.get('route', 'unknown')} "
                f"({', '.join(f'{k}={v}' for k, v in counts.items())})",
                file=sys.stderr,
            )

    dashboard_state = dashboard_state_from_results(results)
    trigger_pr_result = results.get(pr_number) if pr_number else None
    current_pr_result = stored_result(trigger_pr_result) if trigger_pr_result is not None else None
    return DashboardCalculation(
        results=results,
        dashboard_state=dashboard_state,
        trigger_pr_result=trigger_pr_result,
        current_pr_result=current_pr_result,
    )


def reconcile_with_latest_dashboard(
    calculation: DashboardCalculation,
    pr_number: int | None,
    open_pr_numbers: set[int],
) -> tuple[DashboardCalculation, bool]:
    if not pr_number or not calculation.used_cached_dashboard_state:
        return calculation, False

    if calculation.trigger_pr_result is None:
        # The trigger PR is a draft, closed, or was dropped between
        # list_open_prs and the worker run. Drop any stale cached result so
        # the notification job cannot continue treating the PR as routed.
        dashboard_state = load_dashboard_state_cache()
        if dashboard_state.get("_loaded_from_dashboard"):
            previous_pr_result = (dashboard_state.get("prs") or {}).get(str(pr_number))
            if previous_pr_result != calculation.starting_pr_result:
                results = results_from_dashboard_state(dashboard_state, open_pr_numbers)
                return replace(calculation, results=results, dashboard_state=dashboard_state), True
        else:
            dashboard_state = calculation.dashboard_state
        dashboard_state = update_dashboard_state_for_pr(dashboard_state, pr_number, None)
        results = results_from_dashboard_state(dashboard_state, open_pr_numbers)
        return replace(calculation, results=results, dashboard_state=dashboard_state), False

    # Reload the cache so we pick up any concurrent writer's update of
    # other PR slots before we merge in our own.
    latest_dashboard_state = load_dashboard_state_cache()
    previous_pr_result = (latest_dashboard_state.get("prs") or {}).get(str(pr_number))
    dashboard_state = calculation.dashboard_state
    results = calculation.results

    if previous_pr_result == calculation.current_pr_result:
        if latest_dashboard_state.get("_loaded_from_dashboard"):
            dashboard_state = latest_dashboard_state
            results = results_from_dashboard_state(dashboard_state, open_pr_numbers)
        return replace(calculation, results=results, dashboard_state=dashboard_state), True

    if latest_dashboard_state.get("_loaded_from_dashboard") and previous_pr_result != calculation.starting_pr_result:
        results = results_from_dashboard_state(latest_dashboard_state, open_pr_numbers)
        return replace(calculation, results=results, dashboard_state=latest_dashboard_state), True

    if latest_dashboard_state.get("_loaded_from_dashboard"):
        dashboard_state = latest_dashboard_state
    dashboard_state = update_dashboard_state_for_pr(dashboard_state, pr_number, calculation.trigger_pr_result)
    results = results_from_dashboard_state(dashboard_state, open_pr_numbers)
    return replace(calculation, results=results, dashboard_state=dashboard_state), False


def render_dashboard_body(
    prs: list[dict[str, Any]],
    results: dict[int, dict[str, Any]],
    repo: str,
) -> str:
    return render_pr_tables(prs, results, repo)


def update_dashboard(args: argparse.Namespace) -> int:
    repo = detect_repo()
    owner, repo_name = repo.split("/", 1)

    prs = list_open_prs(repo)
    open_pr_numbers = {p["number"] for p in prs}
    if args.pr_number is None:
        prune_classification_cache(open_pr_numbers)
    non_drafts = [p for p in prs if not p.get("isDraft")]

    reviewers = load_reviewer_set(owner)

    calculation = compute_pr_results(
        repo,
        owner,
        repo_name,
        non_drafts,
        open_pr_numbers,
        reviewers,
        args.pr_number,
        DEFAULT_JOBS,
        args.model,
    )

    calculation, dashboard_state_unchanged = reconcile_with_latest_dashboard(
        calculation,
        args.pr_number,
        open_pr_numbers,
    )

    md = render_dashboard_body(
        prs,
        calculation.results,
        repo,
    )
    output_path = dashboard_markdown_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"wrote dashboard markdown to {output_path.resolve()}", file=sys.stderr)

    if dashboard_state_unchanged:
        if args.pr_number:
            print(f"PR #{args.pr_number} dashboard state unchanged", file=sys.stderr)
        else:
            print("dashboard state unchanged", file=sys.stderr)
        return 0

    save_dashboard_state_cache(calculation.dashboard_state)
    return 0


def update_dashboard_with_state(args: argparse.Namespace, state_dir: Path) -> int:
    return state_branch.push_state_changes(
        state_dir,
        "Update dashboard state",
        lambda: update_dashboard(args),
        state_branch=args.state_branch,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--state-branch",
        required=True,
        help="git branch used for workflow state",
    )
    parser.add_argument("--pr-number", type=int, help="only refresh dashboard state for this PR")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"copilot model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()
    with state_branch.temporary_state_dir() as state_dir:
        set_state_dir(state_dir)
        return update_dashboard_with_state(args, state_dir)


if __name__ == "__main__":
    sys.exit(main())
