#!/usr/bin/env python3
"""Mock Claude Code CLI that drives a PreToolUse hook for conformance testing.

Spawned by scenario.py as ClaudeAgentOptions.cli_path so the SDK exercises its
real subprocess + control-protocol path without requiring the actual `claude`
binary or network access.

Unlike the plain claude-agent-sdk mock (one-shot text reply), this mock runs
the *bidirectional* control protocol needed to fire a hook:

  1. SDK -> CLI  control_request {subtype: initialize, hooks: {...}}
       We capture the PreToolUse hookCallbackIds and ack.
  2. SDK -> CLI  {type: user, ...}
       We emit an assistant message containing a Bash tool_use block, then
       send a hook_callback control_request BACK to the SDK so it runs the
       Python PreToolUse hook (the guardrail).
  3. CLI -> SDK  control_request {subtype: hook_callback, callback_id, input}
  4. SDK -> CLI  control_response {response: {hookSpecificOutput: {permissionDecision}}}
       On "deny" we do NOT execute the tool; we emit a tool_result marking it
       blocked, then the final result.

The control-protocol shapes here mirror
claude_agent_sdk/_internal/query.py (initialize hooks_config,
_handle_control_request "hook_callback" branch). Hooks only run in streaming
mode, so scenario.py must use ClaudeSDKClient (not query(prompt=str)).

NOTE: validate on a machine with the real claude-agent-sdk==0.2.149 installed
(public PyPI). The wire details below are derived from SDK source, not yet
run end to end.
"""

import json
import sys

SESSION_ID = "mock-session-guardrail-001"
TOOL_USE_ID = "toolu_mock_guardrail_1"
# A destructive shell command the guardrail is expected to deny.
DANGEROUS_COMMAND = "rm -rf /important/data"

_state = {
    "pretool_callback_ids": [],
    "awaiting_hook_request_id": None,
}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle_initialize(msg: dict) -> None:
    request = msg.get("request", {})
    hooks = request.get("hooks") or {}
    for matcher in hooks.get("PreToolUse", []) or []:
        _state["pretool_callback_ids"].extend(matcher.get("hookCallbackIds", []))
    _emit(
        {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": msg.get("request_id"),
                "response": {},
            },
        }
    )


def _emit_assistant_tool_use() -> None:
    _emit(
        {
            "type": "assistant",
            "message": {
                "id": "msg_mock_guardrail_001",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [
                    {
                        "type": "tool_use",
                        "id": TOOL_USE_ID,
                        "name": "Bash",
                        "input": {"command": DANGEROUS_COMMAND},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 12, "output_tokens": 6},
            },
            "parent_tool_use_id": None,
            "uuid": "00000000-0000-0000-0000-0000000000a1",
            "session_id": SESSION_ID,
        }
    )


def _send_hook_callback() -> None:
    request_id = "cli_hook_req_1"
    _state["awaiting_hook_request_id"] = request_id
    _emit(
        {
            "type": "control_request",
            "request_id": request_id,
            "request": {
                "subtype": "hook_callback",
                "callback_id": _state["pretool_callback_ids"][0],
                "tool_use_id": TOOL_USE_ID,
                "input": {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": DANGEROUS_COMMAND},
                    "tool_use_id": TOOL_USE_ID,
                    "session_id": SESSION_ID,
                    "transcript_path": "/tmp/mock-transcript.jsonl",
                    "cwd": "/tmp",
                    "permission_mode": "default",
                },
            },
        }
    )


def _emit_blocked_result(reason: str) -> None:
    # Deny path: surface the block as a tool_result, then close the turn.
    _emit(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": TOOL_USE_ID,
                        "content": f"Tool call blocked by guardrail: {reason}",
                        "is_error": True,
                    }
                ],
            },
            "parent_tool_use_id": None,
            "uuid": "00000000-0000-0000-0000-0000000000a2",
            "session_id": SESSION_ID,
        }
    )
    _emit(
        {
            "type": "result",
            "subtype": "success",
            "duration_ms": 100,
            "duration_api_ms": 50,
            "is_error": False,
            "num_turns": 1,
            "session_id": SESSION_ID,
            "result": f"Blocked destructive Bash command: {reason}",
            "stop_reason": "tool_use",
            "total_cost_usd": 0.001,
            "usage": {"input_tokens": 12, "output_tokens": 6},
            "modelUsage": {},
            "permission_denials": [{"tool_name": "Bash", "tool_use_id": TOOL_USE_ID}],
        }
    )


def handle_line(line: str) -> None:
    line = line.strip()
    if not line:
        return
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return

    msg_type = msg.get("type")

    if msg_type == "control_request":
        if msg.get("request", {}).get("subtype") == "initialize":
            _handle_initialize(msg)
        else:
            _emit(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": msg.get("request_id"),
                        "response": {},
                    },
                }
            )

    elif msg_type == "control_response":
        response = msg.get("response", {})
        if response.get("request_id") == _state["awaiting_hook_request_id"]:
            _state["awaiting_hook_request_id"] = None
            hook_out = response.get("response", {}) or {}
            specific = hook_out.get("hookSpecificOutput", {}) or {}
            decision = specific.get("permissionDecision", "allow")
            reason = specific.get("permissionDecisionReason", "")
            if decision == "deny":
                _emit_blocked_result(reason)
            else:
                # Allow path (not exercised by the deny scenario, kept for parity).
                _emit_blocked_result("allowed (mock does not execute tools)")

    elif msg_type == "user":
        _emit_assistant_tool_use()
        if _state["pretool_callback_ids"]:
            _send_hook_callback()
        else:
            # No hook registered: close the turn without a guardrail.
            _emit_blocked_result("no PreToolUse hook registered")


def main() -> None:
    for line in sys.stdin:
        handle_line(line)


if __name__ == "__main__":
    main()
