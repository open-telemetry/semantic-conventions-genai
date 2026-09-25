#!/usr/bin/env python3
"""Mock Claude Code CLI for conformance testing.

Spawned by scenario.py as ClaudeAgentOptions.cli_path so the SDK exercises its
real subprocess path without requiring the actual `claude` binary.

Implements the JSON-line protocol expected by claude-agent-sdk:
  stdin  <- SDK sends control_request and user messages (JSON lines)
  stdout -> CLI responds with control_response, assistant, and result messages
"""

import json
import sys

_PERMISSION_PROBE_REQUEST_ID = "permission-probe-1"
_permission_probe_pending = False


def _write_result(*, permission_denials=None, result_text="Hello! I'm a mock Claude response.") -> None:
    result = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 100,
        "duration_api_ms": 50,
        "is_error": False,
        "num_turns": 1,
        "session_id": "mock-session-001",
        "result": result_text,
        "stop_reason": "end_turn",
        "total_cost_usd": 0.001,
        "usage": {"input_tokens": 10, "output_tokens": 8},
        "modelUsage": {},
        "permission_denials": list(permission_denials or []),
    }
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


def handle_line(line: str) -> None:
    global _permission_probe_pending
    line = line.strip()
    if not line:
        return

    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return

    if msg.get("type") == "control_request":
        resp = {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": msg.get("request_id"),
                "response": {},
            },
        }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    elif msg.get("type") == "user":
        message = msg.get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = json.dumps(content)

        if "[permission-probe]" in str(content):
            _permission_probe_pending = True
            request = {
                "type": "control_request",
                "request_id": _PERMISSION_PROBE_REQUEST_ID,
                "request": {
                    "subtype": "can_use_tool",
                    "tool_name": "Bash",
                    "input": {"command": "echo permission-probe"},
                    "permission_suggestions": [],
                    "tool_use_id": "toolu_mock_permission_001",
                    "decision_reason": "mock CLI requests permission before Bash execution",
                    "title": "Claude wants to run a Bash command",
                    "display_name": "Bash",
                    "description": "echo permission-probe",
                },
            }
            sys.stdout.write(json.dumps(request) + "\n")
            sys.stdout.flush()
            return

        assistant = {
            "type": "assistant",
            "message": {
                "id": "msg_mock_001",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "Hello! I'm a mock Claude response."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            "parent_tool_use_id": None,
            "uuid": "00000000-0000-0000-0000-000000000001",
            "session_id": "mock-session-001",
        }
        sys.stdout.write(json.dumps(assistant) + "\n")
        sys.stdout.flush()
        _write_result()

    elif msg.get("type") == "control_response":
        response = msg.get("response") or {}
        if _permission_probe_pending and response.get("request_id") == _PERMISSION_PROBE_REQUEST_ID:
            decision = response.get("response") or {}
            behavior = decision.get("behavior")
            if behavior != "deny":
                raise RuntimeError("permission probe expected the SDK callback to deny the tool")
            _permission_probe_pending = False
            _write_result(
                permission_denials=[
                    {
                        "tool_name": "Bash",
                        "tool_use_id": "toolu_mock_permission_001",
                        "message": decision.get("message", "denied"),
                    }
                ],
                result_text="Permission probe completed.",
            )


def main() -> None:
    for line in sys.stdin:
        handle_line(line)


if __name__ == "__main__":
    main()
