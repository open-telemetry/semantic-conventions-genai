from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from utils import truncate


LLM_THREAD_TIMEOUT_SECONDS = 180
CLASSIFICATION_CACHE_DIR = Path(".cache/classifications")
THREAD_RECENT_COMMENTS_LIMIT = 20
THREAD_COMMENT_BODY_MAX_CHARS = 500
MAX_PROMPT_CHARS = 18_000

THREAD_PROMPT_TEMPLATE = """You are triaging one pull request discussion thread.

Classify ONLY this one thread. You are not deciding the final dashboard section.
The final routing is computed later from deterministic facts and all thread
classifications.

Each thread comment has a deterministic participant_role:
    - author: the PR author
    - reviewer: any non-author human participant
    - bot: automation

Question: who has the next action for this discussion thread?

Use these labels:
  - author: the PR author needs to respond, implement, rebase, or otherwise act
  - reviewer: a reviewer/approver/maintainer needs to review, answer, approve, or merge
  - external: the thread is blocked on something outside this repository
  - none: no follow-up is needed for this thread
  - unclear: the thread does not contain enough information to decide

Guidance:
  - Default heuristic: whoever commented last has passed the ball to the other
    side. If the latest comment is from a reviewer/approver, the author owes a
    response (classify as author). If the latest comment is from the author,
    the reviewer owes a response (classify as reviewer).
  - This applies even to optional suggestions, "for ideas" links, references,
    or links to a reviewer's own pull request / patch with proposed changes.
    The author still needs to acknowledge, accept, or push back.
  - Exceptions that map to none:
    - Purely social comments ("thanks", "LGTM", "nice work") with no follow-up
      requested or implied.
    - The reviewer's last comment is a clear acknowledgement of the author's
      previous reply ("sounds good", "ok thanks") that closes the thread.
  - Exception that keeps the ball with the author: if the author's latest
    comment is a self-deferral ("still working on it", "WIP", "I'll get to
    this", "will fix") rather than a question or completed reply, classify as
    author — they have not yet handed the ball back.

Respond with a single JSON object and nothing else:
{{"thread_action": "author" | "reviewer" | "external" | "none" | "unclear", "reason": "short explanation grounded in this thread"}}

---BEGIN THREAD---
{thread}
---END THREAD---
"""


def parse_copilot_jsonl(s: str) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    usage: dict[str, Any] = {}
    for line in s.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "assistant.message":
            content = (evt.get("data") or {}).get("content")
            if isinstance(content, str):
                parts.append(content)
        elif evt.get("type") == "result":
            usage_obj = evt.get("usage") or {}
            if isinstance(usage_obj.get("premiumRequests"), int):
                usage["premium_requests"] = usage_obj["premiumRequests"]
    return "\n".join(parts), usage


def extract_json_object(s: str) -> dict[str, Any] | None:
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    i = 0
    while i < len(s):
        j = s.find("{", i)
        if j == -1:
            break
        try:
            obj, end = decoder.raw_decode(s, j)
        except json.JSONDecodeError:
            i = j + 1
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        i = end
    return objects[-1] if objects else None


def normalize_thread_action(action: str) -> str:
    action = (action or "").lower().strip()
    if action in ("author", "reviewer", "external", "none", "unclear"):
        return action
    if action == "approver":
        return "reviewer"
    return "unclear"


def parse_thread_decision(response_text: str) -> tuple[dict[str, str], bool]:
    obj = extract_json_object(response_text) if response_text else None
    if not obj:
        return {"thread_action": "unclear", "reason": "LLM did not return valid JSON"}, False
    raw_action = str(obj.get("thread_action") or obj.get("route") or "")
    action = normalize_thread_action(raw_action)
    valid_action = raw_action.lower().strip() in (
        "author",
        "reviewer",
        "external",
        "none",
        "unclear",
        "approver",
    )
    reason = truncate(str(obj.get("reason") or ""), 300)
    if not reason:
        reason = "No reason provided"
    return {"thread_action": action, "reason": reason}, valid_action


def is_conflict_resolution_comment(body: str) -> bool:
    text = (body or "").lower()
    return "conflict" in text and any(word in text for word in ("resolve", "resolved", "merge"))


def participant_role(actor_role: str) -> str:
    if actor_role == "author":
        return "author"
    if actor_role == "bot":
        return "bot"
    return "reviewer"


def thread_prompt_input(thread: dict[str, Any]) -> dict[str, Any]:
    prompt_thread = {
        key: value
        for key, value in thread.items()
        if key != "comments"
    }
    prompt_thread["comments"] = [
        {
            "timestamp": comment.get("timestamp") or "",
            "actor": comment.get("actor") or "",
            "participant_role": participant_role(comment.get("actor_role") or ""),
            "body": comment.get("body") or "",
        }
        for comment in (thread.get("comments") or [])
    ]
    return prompt_thread


def thread_prompt(thread: dict[str, Any]) -> str:
    prompt_thread = thread_prompt_input(thread)
    thread_text = json.dumps(prompt_thread, indent=2, sort_keys=True)
    prompt = THREAD_PROMPT_TEMPLATE.format(thread=thread_text)
    if len(prompt) <= MAX_PROMPT_CHARS:
        return prompt
    trimmed = dict(prompt_thread)
    comments = [dict(c) for c in prompt_thread.get("comments") or []]
    for c in comments:
        c["body"] = truncate(c.get("body") or "", THREAD_COMMENT_BODY_MAX_CHARS)
    trimmed["comments"] = comments[-THREAD_RECENT_COMMENTS_LIMIT:]
    thread_text = json.dumps(trimmed, indent=2, sort_keys=True)
    return THREAD_PROMPT_TEMPLATE.format(thread=thread_text)


def run_llm_for_thread(thread: dict[str, Any], model: str) -> dict[str, Any]:
    prompt = thread_prompt(thread)
    proc = subprocess.run(
        ["copilot", "-p", prompt, "--output-format", "json", "--model", model],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=LLM_THREAD_TIMEOUT_SECONDS,
    )
    response_text, usage = parse_copilot_jsonl(proc.stdout)
    decision, valid_response = parse_thread_decision(response_text)
    return {
        "thread_id": thread["thread_id"],
        "thread_kind": thread["thread_kind"],
        "failed": proc.returncode != 0 or not valid_response,
        "decision": decision,
        "usage": usage,
        "error": proc.stderr[-2000:] if proc.stderr else "",
        "response_text": response_text,
    }


def thread_cache_key(thread: dict[str, Any], model: str) -> str:
    cache_key_json = json.dumps(
        {
            "model": model,
            "prompt_template": THREAD_PROMPT_TEMPLATE,
            "thread": thread_prompt_input(thread),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(cache_key_json.encode("utf-8")).hexdigest()


def load_classification_cache(pr_number: int) -> dict[str, dict[str, Any]]:
    path = CLASSIFICATION_CACHE_DIR / f"{pr_number}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  warning: ignoring unreadable classification cache {path}: {e!r}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_classification_cache(pr_number: int, cache: dict[str, dict[str, Any]]) -> None:
    CLASSIFICATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CLASSIFICATION_CACHE_DIR / f"{pr_number}.json"
    path.write_text(json.dumps(cache, sort_keys=True, indent=2), encoding="utf-8")


def prune_classification_cache(open_pr_numbers: set[int]) -> None:
    if not CLASSIFICATION_CACHE_DIR.exists():
        return
    for path in CLASSIFICATION_CACHE_DIR.glob("*.json"):
        if not path.stem.isdigit():
            continue
        if int(path.stem) not in open_pr_numbers:
            path.unlink()


def classify_threads(number: int, threads: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    cache_in = load_classification_cache(number)
    cache_out: dict[str, dict[str, Any]] = {}
    classifications: list[dict[str, Any]] = []
    for thread in threads:
        key = thread_cache_key(thread, model)
        cached = cache_in.get(key)
        if isinstance(cached, dict):
            record = dict(cached)
            record["thread_id"] = thread["thread_id"]
            record["thread_kind"] = thread["thread_kind"]
            classifications.append(record)
            cache_out[key] = cached
            continue
        try:
            record = run_llm_for_thread(thread, model)
        except subprocess.TimeoutExpired:
            record = {
                "thread_id": thread["thread_id"],
                "thread_kind": thread["thread_kind"],
                "failed": True,
                "decision": {"thread_action": "unclear", "reason": "LLM timeout"},
                "error": "timeout",
            }
        except Exception as e:
            print(
                f"  warning: thread {thread['thread_id']} on PR #{number} failed to classify:",
                file=sys.stderr,
            )
            traceback.print_exc()
            record = {
                "thread_id": thread["thread_id"],
                "thread_kind": thread["thread_kind"],
                "failed": True,
                "decision": {"thread_action": "unclear", "reason": f"LLM failed: {e!r}"},
                "error": repr(e),
            }
        classifications.append(record)
        if not record.get("failed"):
            cache_out[key] = record
    save_classification_cache(number, cache_out)
    return classifications
