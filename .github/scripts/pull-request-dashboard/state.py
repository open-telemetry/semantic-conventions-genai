from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


DASHBOARD_MARKDOWN_FILE = "pull-request-dashboard.md"
_state_dir: Path | None = None


def set_state_dir(path: Path) -> None:
    global _state_dir
    _state_dir = path


def state_dir() -> Path:
    if _state_dir is None:
        raise RuntimeError("state directory has not been initialized")
    return _state_dir


def dashboard_state_path() -> Path:
    return state_dir() / "dashboard-state.json"


def notification_state_path() -> Path:
    return state_dir() / "notification-state.json"


def dashboard_markdown_path() -> Path:
    return state_dir() / DASHBOARD_MARKDOWN_FILE


def empty_state() -> dict[str, Any]:
    return {"version": 1, "prs": {}, "_loaded_from_dashboard": False}


def load_state_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"warning: ignoring unreadable state file {path}: {e!r}",
            file=sys.stderr,
        )
        return empty_state()
    if not isinstance(data, dict):
        return empty_state()
    if not isinstance(data.get("prs"), dict):
        data["prs"] = {}
    data["version"] = 1
    data["_loaded_from_dashboard"] = True
    return data


def save_state_file(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = {k: v for k, v in state.items() if not k.startswith("_")}
    stored.setdefault("version", 1)
    stored.setdefault("prs", {})
    path.write_text(json.dumps(stored, sort_keys=True, indent=2), encoding="utf-8")


def load_dashboard_state_cache() -> dict[str, Any]:
    return load_state_file(dashboard_state_path())


def save_dashboard_state_cache(state: dict[str, Any]) -> None:
    save_state_file(dashboard_state_path(), state)


def load_notification_state_file() -> dict[str, Any]:
    return load_state_file(notification_state_path())


def save_notification_state_file(state: dict[str, Any]) -> None:
    save_state_file(notification_state_path(), state)


def union_merge_notification_state(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Union-merge `overlay`'s per-PR entries into `base`.

    For each PR, the entry with the newer `last_notified_at` wins.
    Used by the workflow's CAS retry loop: an earlier attempt's
    just-sent notification state is carried into the next attempt so
    the cadence gate sees those pings as already-notified after a
    reset to the remote tip.
    """
    base_prs = dict(base.get("prs") or {})
    for pr_key, overlay_entry in (overlay.get("prs") or {}).items():
        base_entry = base_prs.get(pr_key)
        if base_entry is None:
            base_prs[pr_key] = overlay_entry
            continue
        overlay_ts = (overlay_entry or {}).get("last_notified_at") or ""
        base_ts = base_entry.get("last_notified_at") or ""
        if overlay_ts > base_ts:
            base_prs[pr_key] = overlay_entry
    merged = dict(base)
    merged["prs"] = base_prs
    return merged


def stored_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "pr_number": result.get("pr_number"),
        "pr_url": result.get("pr_url") or "",
        "failed": bool(result.get("failed")),
        "route": result.get("route") or "unknown",
        "facts": result.get("facts") or {},
    }


def results_from_dashboard_state(state: dict[str, Any], open_pr_numbers: set[int]) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    for key, value in (state.get("prs") or {}).items():
        if not isinstance(value, dict):
            continue
        try:
            number = int(key)
        except ValueError:
            continue
        if number in open_pr_numbers:
            results[number] = value
    return results


def dashboard_state_from_results(results: dict[int, dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "prs": {str(number): stored_result(result) for number, result in sorted(results.items())},
        "_loaded_from_dashboard": True,
    }


def update_dashboard_state_for_pr(
    state: dict[str, Any],
    number: int,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    prs = dict(state.get("prs") or {})
    key = str(number)
    if result is None:
        prs.pop(key, None)
    else:
        prs[key] = stored_result(result)
    return {
        "version": 1,
        "prs": prs,
        "_loaded_from_dashboard": bool(state.get("_loaded_from_dashboard")),
    }