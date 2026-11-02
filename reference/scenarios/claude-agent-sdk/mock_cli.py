#!/usr/bin/env python3
"""Mock Claude Code CLI for conformance testing.

Spawned by scenario.py as ClaudeAgentOptions.cli_path so the SDK exercises its
real subprocess path without requiring the actual `claude` binary.

Implements the JSON-line protocol expected by claude-agent-sdk:
  stdin  <- SDK sends control_request and user messages (JSON lines)
  stdout -> CLI responds with control_response, system, assistant, user, and
            result messages, and sends hook_callback control requests

When started with `--plugin-dir`, the mock loads each plugin manifest the way
Claude Code does, lists the plugin and its namespaced skills in the `init`
system message, and runs one `Skill` tool call for the first plugin skill
between PreToolUse and PostToolUse hook callbacks.
"""

import json
import os
import sys

SESSION_ID = "mock-session-001"
MODEL = "claude-sonnet-4-20250514"

hook_callback_ids: dict[str, list[str]] = {}
control_request_counter = 0


def write(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def plugin_dirs_from_argv() -> list[str]:
    plugin_dirs = []
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--plugin-dir" and index + 1 < len(args):
            plugin_dirs.append(args[index + 1])
    return plugin_dirs


def load_plugins(plugin_dirs: list[str]) -> tuple[list[dict], list[str]]:
    plugins = []
    skills = []
    for plugin_dir in plugin_dirs:
        manifest_path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
        with open(manifest_path, encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        plugin = {"name": manifest["name"], "path": plugin_dir}
        if "version" in manifest:
            plugin["version"] = manifest["version"]
        plugins.append(plugin)
        skills_dir = os.path.join(plugin_dir, "skills")
        for skill_dir_name in sorted(os.listdir(skills_dir)):
            skills.append(f"{manifest['name']}:{skill_dir_name}")
    return plugins, skills


def read_message() -> dict | None:
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        return json.loads(line)


def run_hooks(event_name: str, hook_input: dict, tool_use_id: str) -> None:
    global control_request_counter
    for callback_id in hook_callback_ids.get(event_name, []):
        control_request_counter += 1
        request_id = f"cli_req_{control_request_counter}"
        write(
            {
                "type": "control_request",
                "request_id": request_id,
                "request": {
                    "subtype": "hook_callback",
                    "callback_id": callback_id,
                    "input": hook_input,
                    "tool_use_id": tool_use_id,
                },
            }
        )
        while True:
            message = read_message()
            if message is None:
                return
            if message.get("type") == "control_response" and message["response"].get("request_id") == request_id:
                break


def handle_control_request(msg: dict) -> None:
    request = msg.get("request") or {}
    if request.get("subtype") == "initialize":
        for event_name, matchers in (request.get("hooks") or {}).items():
            for matcher in matchers:
                hook_callback_ids.setdefault(event_name, []).extend(matcher.get("hookCallbackIds", []))
    write(
        {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": msg.get("request_id"),
                "response": {},
            },
        }
    )


def write_result(result_text: str, num_turns: int) -> None:
    write(
        {
            "type": "result",
            "subtype": "success",
            "duration_ms": 100,
            "duration_api_ms": 50,
            "is_error": False,
            "num_turns": num_turns,
            "session_id": SESSION_ID,
            "result": result_text,
            "stop_reason": "end_turn",
            "total_cost_usd": 0.001,
            "usage": {"input_tokens": 10, "output_tokens": 8},
            "modelUsage": {},
            "permission_denials": [],
        }
    )


def write_assistant(message_id: str, message_uuid: str, content: list[dict], stop_reason: str) -> None:
    write(
        {
            "type": "assistant",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": content,
                "stop_reason": stop_reason,
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            "parent_tool_use_id": None,
            "uuid": message_uuid,
            "session_id": SESSION_ID,
        }
    )


def handle_basic_turn() -> None:
    text = "Hello! I'm a mock Claude response."
    write_assistant(
        "msg_mock_001", "00000000-0000-0000-0000-000000000001", [{"type": "text", "text": text}], "end_turn"
    )
    write_result(text, 1)


def handle_plugin_skill_turn(plugins: list[dict], skills: list[str]) -> None:
    cwd = os.getcwd()
    write(
        {
            "type": "system",
            "subtype": "init",
            "uuid": "00000000-0000-0000-0000-000000000010",
            "session_id": SESSION_ID,
            "apiKeySource": "none",
            "claude_code_version": "mock",
            "cwd": cwd,
            "tools": ["Skill"],
            "mcp_servers": [],
            "model": MODEL,
            "permissionMode": "bypassPermissions",
            "slash_commands": [],
            "output_style": "default",
            "skills": skills,
            "plugins": plugins,
        }
    )

    tool_use_id = "toolu_mock_001"
    tool_input = {"skill": skills[0]}
    write_assistant(
        "msg_mock_002",
        "00000000-0000-0000-0000-000000000002",
        [{"type": "tool_use", "id": tool_use_id, "name": "Skill", "input": tool_input}],
        "tool_use",
    )

    base_hook_input = {
        "session_id": SESSION_ID,
        "transcript_path": os.path.join(cwd, "mock-transcript.jsonl"),
        "cwd": cwd,
        "permission_mode": "bypassPermissions",
        "tool_name": "Skill",
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
    }
    run_hooks("PreToolUse", {**base_hook_input, "hook_event_name": "PreToolUse"}, tool_use_id)
    tool_response = f"Launching skill: {skills[0]}"
    run_hooks(
        "PostToolUse",
        {**base_hook_input, "hook_event_name": "PostToolUse", "tool_response": tool_response},
        tool_use_id,
    )

    write(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": tool_response}],
            },
            "parent_tool_use_id": None,
            "uuid": "00000000-0000-0000-0000-000000000011",
            "session_id": SESSION_ID,
        }
    )

    text = "Release notes drafted."
    write_assistant(
        "msg_mock_003", "00000000-0000-0000-0000-000000000003", [{"type": "text", "text": text}], "end_turn"
    )
    write_result(text, 2)


def main() -> None:
    plugins, skills = load_plugins(plugin_dirs_from_argv())
    while True:
        msg = read_message()
        if msg is None:
            return
        if msg.get("type") == "control_request":
            handle_control_request(msg)
        elif msg.get("type") == "user":
            if skills:
                handle_plugin_skill_turn(plugins, skills)
            else:
                handle_basic_turn()


if __name__ == "__main__":
    main()
