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


def handle_line(line: str) -> None:
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

        result = {
            "type": "result",
            "subtype": "success",
            "duration_ms": 100,
            "duration_api_ms": 50,
            "is_error": False,
            "num_turns": 1,
            "session_id": "mock-session-001",
            "result": "Hello! I'm a mock Claude response.",
            "stop_reason": "end_turn",
            "total_cost_usd": 0.001,
            "usage": {"input_tokens": 10, "output_tokens": 8},
            "modelUsage": {},
            "permission_denials": [],
        }
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        handle_line(line)


if __name__ == "__main__":
    main()
