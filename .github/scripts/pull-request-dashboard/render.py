from __future__ import annotations

from datetime import datetime
from typing import Any

from utils import actor_login, activity_age, parse_ts, seconds_since


ROUTE_LABELS = {
    "maintainer": "Waiting on maintainers",
    "approver": "Waiting on approvers",
    "author": "Waiting on authors",
    "external": "Waiting on external",
    "transient-failure": "Transient GitHub failure retrieving PR data",
    "unknown": "Unknown",
}
ROUTE_ORDER = ["maintainer", "approver", "author", "external", "transient-failure", "unknown"]


def _md_escape(s: str) -> str:
    return (
        (s or "")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("@", "&#64;")
        .replace("\n", " ")
        .strip()
    )


def render_draft_pr_section(prs: list[dict[str, Any]]) -> list[str]:
    drafts = [p for p in prs if p.get("isDraft")]
    if not drafts:
        return []
    drafts.sort(key=lambda p: p.get("updatedAt") or "")
    lines = ["## Draft pull requests", ""]
    lines.append("| PR | Author | Updated |")
    lines.append("|---|---|:---:|")
    for pr in drafts:
        number = pr["number"]
        title = _md_escape(pr.get("title", ""))
        url = pr.get("url", "")
        author = actor_login(pr.get("author") or {})
        updated = activity_age(parse_ts(pr.get("updatedAt") or ""))
        lines.append(f"| [{title} (#{number})]({url}) | {author} | {updated} |")
    lines.append("")
    return lines


def ci_cell(facts: dict[str, Any]) -> str:
    if "ci_failing_count" not in facts and "ci_pending_count" not in facts:
        return "?"
    if facts.get("ci_failing_count", 0) > 0:
        return "❌"
    if facts.get("ci_pending_count", 0) > 0:
        return "⏳"
    return "✅"


def conflicts_cell(facts: dict[str, Any]) -> str:
    conflicts = facts.get("conflicts")
    if conflicts == "yes":
        return "❌"
    if conflicts == "no":
        return "✅"
    return "?"


def _age_ts(facts: dict[str, Any]) -> datetime | None:
    return parse_ts(facts.get("waiting_since") or facts.get("last_activity_at") or "")


def age_seconds(facts: dict[str, Any]) -> int | None:
    return seconds_since(_age_ts(facts))


def age_cell(facts: dict[str, Any]) -> str:
    return activity_age(_age_ts(facts))


def _neutralize_code_fence(s: str) -> str:
    return (s or "").replace("```", "`\u200d`\u200d`")


def render_diagnostics_section(results: dict[int, dict[str, Any]]) -> list[str]:
    data_lines: list[str] = []
    for number in sorted(results, reverse=True):
        result = results[number]
        classifications = result.get("classifications") or []
        error = result.get("error")
        if not classifications and not error:
            continue
        data_lines.append(f"PR #{number}")
        for c in classifications:
            decision = c.get("decision") or {}
            reason = (decision.get("reason") or "").replace("\n", " ")
            data_lines.append(f"llm: {c.get('thread_id')} -> {decision.get('thread_action')} ({reason})")
        if error:
            data_lines.append(f"error: {error}")
        data_lines.append("")
    return [
        "<details>",
        "<summary>Diagnostics</summary>",
        "",
        "```text",
        *(_neutralize_code_fence(line) for line in data_lines),
        "```",
        "",
        "</details>",
        "",
    ]


def render_pr_tables(prs: list[dict[str, Any]], results: dict[int, dict[str, Any]], repo: str) -> str:
    source_url = f"https://github.com/{repo}/blob/main/.github/scripts/pull-request-dashboard/dashboard.py"
    refresh_url = f"https://github.com/{repo}/actions/workflows/pull-request-dashboard.yml"
    out: list[str] = [
        "> [!NOTE]",
        "> Open non-draft PRs grouped by who is expected to act next. Draft PRs are "
        "listed separately. The grouping is "
        f"partly performed by an LLM ([source]({source_url})) and could contain mistakes.",
        "",
    ]

    by_route: dict[str, list[dict[str, Any]]] = {}
    for pr in prs:
        if pr.get("isDraft"):
            continue
        res = results.get(pr["number"]) or {"route": "unknown"}
        route = res.get("route") or "unknown"
        if route not in ROUTE_ORDER:
            route = "unknown"
        by_route.setdefault(route, []).append(pr)

    def row_sort_key(pr: dict[str, Any]) -> tuple[int, int]:
        res = results.get(pr["number"]) or {}
        facts = res.get("facts") or {}
        activity = age_seconds(facts)
        return (activity if activity is not None else -1, pr["number"])

    for route in ROUTE_ORDER:
        rows = by_route.get(route) or []
        if not rows:
            continue
        rows.sort(key=row_sort_key, reverse=True)
        out.append(f"## {ROUTE_LABELS.get(route, route)}")
        out.append("")
        out.append("| PR | Author | Assignees | CI | Conflicts | Age |")
        out.append("|---|---|---|:---:|:---:|:---:|")
        for pr in rows:
            number = pr["number"]
            title = _md_escape(pr.get("title", ""))
            url = pr.get("url", "")
            res = results.get(number) or {}
            facts = res.get("facts") or {}
            author = facts.get("author") or actor_login(pr.get("author") or {})
            assignees = facts.get("assignees") or [
                actor_login(a) for a in (pr.get("assignees") or [])
            ]
            assignees_cell = _md_escape(", ".join(a for a in assignees if a))
            activity_cell = age_cell(facts)
            pr_cell = f"[{title} (#{number})]({url})"
            if facts.get("approved"):
                pr_cell += " ✅"
            out.append(
                f"| {pr_cell} | {author} | {assignees_cell} | {ci_cell(facts)} | "
                f"{conflicts_cell(facts)} | {activity_cell} |"
            )
        out.append("")

    out.extend(render_draft_pr_section(prs))
    out.extend(render_diagnostics_section(results))
    out.append(f"_Approvers may [force a refresh]({refresh_url})._")
    out.append("")
    return "\n".join(out) + "\n"
