"""Slack notification timing for the PR dashboard."""

from __future__ import annotations

from datetime import datetime
import html
import json
import os
import sys
import time
from typing import Any
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from utils import activity_age, format_ts, parse_ts


NOTIFICATION_TIME_ZONE = ZoneInfo("America/Los_Angeles")
REVIEWER_FOLLOW_UP_SECONDS = 24 * 60 * 60
SLACK_WEBHOOK_RETRY_ATTEMPTS = 3
SLACK_WEBHOOK_RETRY_DELAY_SECONDS = 1.0


def load_slack_user_map() -> dict[str, str]:
    raw = os.environ.get("SLACK_USER_MAP_JSON") or ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"SLACK_USER_MAP_JSON must be valid JSON: {e.msg} at char {e.pos}") from e
    if not isinstance(data, dict):
        raise RuntimeError("SLACK_USER_MAP_JSON must be a JSON object mapping GitHub logins to Slack user IDs")
    return {str(k).lower(): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}


def slack_webhook_retry_delay(attempt: int, e: urllib.error.HTTPError | None = None) -> float:
    if e is not None:
        retry_after = e.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
    return min(SLACK_WEBHOOK_RETRY_DELAY_SECONDS * (2**attempt), 30.0)


def should_retry_slack_http_error(e: urllib.error.HTTPError) -> bool:
    return e.code == 429 or 500 <= e.code < 600


def is_notification_weekday(now: datetime) -> bool:
    return now.astimezone(NOTIFICATION_TIME_ZONE).weekday() < 5


def post_slack_webhook(message: str, webhook_url: str) -> None:
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": message, "unfurl_links": False}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    for attempt in range(SLACK_WEBHOOK_RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if attempt + 1 < SLACK_WEBHOOK_RETRY_ATTEMPTS and should_retry_slack_http_error(e):
                time.sleep(slack_webhook_retry_delay(attempt, e))
                continue
            raise RuntimeError(f"Slack webhook request failed with HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            if attempt + 1 < SLACK_WEBHOOK_RETRY_ATTEMPTS:
                time.sleep(slack_webhook_retry_delay(attempt))
                continue
            raise RuntimeError(f"Slack webhook request failed: {e}") from e
        if body.strip().lower() != "ok":
            raise RuntimeError(f"Slack webhook request failed: {body}")
        return


def slack_escape_link_text(text: str) -> str:
    # Slack link text requires escaping &, <, and >.
    # Other PR title punctuation can be rendered as-is.
    return html.escape(text, quote=False)


def slack_message(repo: str, result: dict[str, Any], reviewer_mentions: str, kind: str) -> str:
    facts = result.get("facts") or {}
    number = result.get("pr_number")
    url = result.get("pr_url") or f"https://github.com/{repo}/pull/{number}"
    title = slack_escape_link_text(str(result.get("pr_title") or "").strip())
    pr_link_text = f"{title} (#{number})" if title else f"PR #{number}"
    if kind == "follow-up":
        waiting_age = activity_age(parse_ts(facts.get("waiting_since") or ""))
        waiting_suffix = f" ({waiting_age})" if waiting_age != "?" else ""
        lead = f"waiting on reviewers{waiting_suffix}"
    else:
        lead = "moved to waiting on reviewers"
    return f"{reviewer_mentions} - {lead}: <{url}|{pr_link_text}>"


def pending_notification_kind(
    previous_state_exists: bool,
    previous_pr_state: dict[str, Any],
    current_waiting_since: datetime | None,
    now: datetime,
) -> str | None:
    if not previous_state_exists:
        return None
    if current_waiting_since is None:
        return None
    last_notified = parse_ts(previous_pr_state.get("last_notified_at") or "")
    if last_notified is None:
        return "initial"
    elapsed_seconds = (now - last_notified).total_seconds()
    if current_waiting_since > last_notified:
        if elapsed_seconds < REVIEWER_FOLLOW_UP_SECONDS:
            return None
        return "initial"
    if is_notification_weekday(now) and elapsed_seconds >= REVIEWER_FOLLOW_UP_SECONDS:
        return "follow-up"
    return None


def reviewer_logins_for_notification(facts: dict[str, Any]) -> list[str]:
    return [
        str(reviewer.get("login") or "")
        for reviewer in (facts.get("reviewers") or [])
        if isinstance(reviewer, dict)
        and reviewer.get("login")
        and (
            not (reviewer.get("approved") or reviewer.get("approved_non_team"))
            or reviewer.get("open_thread")
        )
    ]


def send_slack_notification(
    repo: str,
    result: dict[str, Any],
    reviewers: list[str],
    kind: str,
    webhook_url: str,
    reviewer_mentions: str,
) -> str | None:
    number = result.get("pr_number")
    if not webhook_url:
        return "SLACK_WEBHOOK_URL is not set"
    try:
        post_slack_webhook(slack_message(repo, result, reviewer_mentions, kind), webhook_url)
    except Exception as e:
        reviewer_list = ", ".join(f"@{reviewer}" for reviewer in reviewers)
        return f"PR #{number}: failed to notify {reviewer_list}: {e}"
    print(
        f"  mentioned {', '.join(f'@{reviewer}' for reviewer in reviewers)} on Slack for PR #{number} ({kind})",
        file=sys.stderr,
    )
    return None


def migrated_pr_notification_state(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("last_notified_at") or not state.get("assignee_notifications"):
        return state
    timestamps: list[str] = []
    for notification in state["assignee_notifications"].values():
        if not isinstance(notification, dict):
            continue
        last_notified_at = notification.get("last_notified_at")
        if isinstance(last_notified_at, str) and last_notified_at:
            timestamps.append(last_notified_at)
    if not timestamps:
        return state
    return {
        "last_notified_at": max(timestamps),
        "last_notification_kind": "initial",
    }


def next_notification_state(
    repo: str,
    results: dict[int, dict[str, Any]],
    previous_state: dict[str, Any],
    now: datetime,
    notification_numbers: set[int] | None = None,
) -> dict[str, Any]:
    previous_prs = previous_state.get("prs") or {}
    previous_state_exists = bool(previous_state.get("_loaded_from_dashboard"))
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL") or ""
    slack_user_map = load_slack_user_map()

    new_prs: dict[str, Any] = {}
    notification_errors: list[str] = []
    for number, result in sorted(results.items()):
        pr_key = str(number)
        previous_pr_state = migrated_pr_notification_state(previous_prs.get(pr_key) or {})

        if notification_numbers is not None and number not in notification_numbers:
            if previous_pr_state:
                new_prs[pr_key] = previous_pr_state
            continue

        route = result.get("route") or "unknown"
        if result.get("failed") or route in ("transient-failure", "unknown"):
            if previous_pr_state:
                new_prs[pr_key] = previous_pr_state
            continue

        if route != "approver":
            continue

        facts = result.get("facts") or {}
        mapped_reviewers = [
            (reviewer, slack_user_map[reviewer.lower()])
            for reviewer in reviewer_logins_for_notification(facts)
            if reviewer.lower() in slack_user_map
        ]
        if not mapped_reviewers:
            if previous_pr_state:
                new_prs[pr_key] = previous_pr_state
            continue

        current_waiting_since = parse_ts(facts.get("waiting_since") or "")
        kind = pending_notification_kind(
            previous_state_exists, previous_pr_state, current_waiting_since, now,
        )

        new_pr_state: dict[str, Any] = {
            "last_notified_at": previous_pr_state.get("last_notified_at") or "",
            "last_notification_kind": previous_pr_state.get("last_notification_kind") or "",
        }

        if kind:
            reviewers = [reviewer for reviewer, _ in mapped_reviewers]
            reviewer_mentions = " ".join(f"<@{slack_user_id}>" for _, slack_user_id in mapped_reviewers)
            error = send_slack_notification(repo, result, reviewers, kind, webhook_url, reviewer_mentions)
            if error:
                print(f"  warning: {error}", file=sys.stderr)
                notification_errors.append(error)
            else:
                new_pr_state["last_notified_at"] = format_ts(now)
                new_pr_state["last_notification_kind"] = kind

        if new_pr_state["last_notified_at"]:
            new_prs[pr_key] = new_pr_state
    return {"version": 1, "prs": new_prs, "_notification_errors": notification_errors}
