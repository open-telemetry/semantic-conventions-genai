"""Reference implementation for Claude Agent SDK."""

import json
import os

from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_CLI_PATH = os.path.join(
    _SCRIPT_DIR,
    "mock_cli.cmd" if os.name == "nt" else "mock_cli.py",
)
PLUGIN_PATH = os.path.join(_SCRIPT_DIR, "plugins", "deploy-tools")

_reference_tracer = reference_tracer()


async def run_agent_query_reference():
    """Scenario: basic agent query via mock CLI with reference implementation."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    print("  [agent_query] basic query via mock CLI (reference implementation)")

    if os.name != "nt":
        os.chmod(MOCK_CLI_PATH, os.stat(MOCK_CLI_PATH).st_mode | 0o111)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"

    options = ClaudeAgentOptions(
        cli_path=MOCK_CLI_PATH,
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    prompt_text = "Say hello."
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
    }
    with _reference_tracer.start_as_current_span("chat", kind=SpanKind.CLIENT, attributes=span_attributes) as span:
        span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt_text}]}])
        )
        output_text = ""
        response_model = None
        response_id = None
        finish_reason = None
        input_tokens = None
        output_tokens = None
        async for message in query(prompt=prompt_text, options=options):
            if isinstance(message, AssistantMessage):
                response_model = response_model or getattr(message, "model", None)
                response_id = response_id or getattr(message, "message_id", None)
                finish_reason = finish_reason or getattr(message, "stop_reason", None)
                msg_usage = getattr(message, "usage", None)
                if msg_usage is not None and input_tokens is None:
                    input_tokens = msg_usage.get("input_tokens")
                    output_tokens = msg_usage.get("output_tokens")
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_text += block.text
                        print(f"    -> {block.text[:60]}")
            elif isinstance(message, ResultMessage):
                finish_reason = finish_reason or getattr(message, "stop_reason", None)
                msg_usage = getattr(message, "usage", None)
                if msg_usage is not None and input_tokens is None:
                    input_tokens = msg_usage.get("input_tokens")
                    output_tokens = msg_usage.get("output_tokens")
                print(f"    -> result: turns={message.num_turns}")
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(finish_reason)])
        if input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if output_text:
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": output_text}],
                        }
                    ]
                ),
            )


async def run_plugin_skill_reference():
    """Scenario: a plugin-provided skill loaded through the `Skill` tool.

    Claude Code runs tools inside the CLI subprocess, but it calls the SDK's
    `PreToolUse` and `PostToolUse` hook callbacks in-process around each tool
    execution. The `execute_tool` span opens and closes in those callbacks.

    The `init` system message lists the plugins the CLI loaded from
    `ClaudeAgentOptions.plugins`, and Claude Code addresses plugin skills as
    `<plugin>:<skill>`, so the `Skill` tool input names the plugin that
    provides the skill.
    """
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, SystemMessage, query

    print("  [plugin_skill] plugin skill via mock CLI (reference implementation)")

    if os.name != "nt":
        os.chmod(MOCK_CLI_PATH, os.stat(MOCK_CLI_PATH).st_mode | 0o111)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"

    loaded_plugins_by_name = {}
    tool_spans_by_tool_use_id = {}

    async def on_pre_tool_use(hook_input, tool_use_id, context):
        attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": hook_input["tool_name"],
            "gen_ai.tool.call.id": tool_use_id,
            "gen_ai.conversation.id": hook_input["session_id"],
        }
        span_name = f"execute_tool {hook_input['tool_name']}"
        if hook_input["tool_name"] == "Skill":
            plugin_name, separator, skill_name = hook_input["tool_input"]["skill"].partition(":")
            if separator:
                attributes["gen_ai.skill.name"] = skill_name
                plugin = loaded_plugins_by_name.get(plugin_name)
                if plugin is not None:
                    attributes["gen_ai.plugin.name"] = plugin["name"]
                    if "version" in plugin:
                        attributes["gen_ai.plugin.version"] = plugin["version"]
            else:
                attributes["gen_ai.skill.name"] = plugin_name
            span_name = f"execute_tool {hook_input['tool_name']} {attributes['gen_ai.skill.name']}"
        tool_spans_by_tool_use_id[tool_use_id] = _reference_tracer.start_span(
            span_name, kind=SpanKind.INTERNAL, attributes=attributes
        )
        return {}

    async def on_post_tool_use(hook_input, tool_use_id, context):
        span = tool_spans_by_tool_use_id.pop(tool_use_id)
        span.end()
        return {}

    async def on_post_tool_use_failure(hook_input, tool_use_id, context):
        span = tool_spans_by_tool_use_id.pop(tool_use_id)
        span.set_attribute("error.type", "tool_error")
        span.set_status(StatusCode.ERROR, hook_input["error"])
        span.end()
        return {}

    options = ClaudeAgentOptions(
        cli_path=MOCK_CLI_PATH,
        max_turns=2,
        permission_mode="bypassPermissions",
        plugins=[{"type": "local", "path": PLUGIN_PATH}],
        hooks={
            "PreToolUse": [HookMatcher(hooks=[on_pre_tool_use])],
            "PostToolUse": [HookMatcher(hooks=[on_post_tool_use])],
            "PostToolUseFailure": [HookMatcher(hooks=[on_post_tool_use_failure])],
        },
    )

    async for message in query(prompt="Draft the release notes.", options=options):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            for plugin in message.data["plugins"]:
                loaded_plugins_by_name[plugin["name"]] = plugin


def main():
    import anyio

    print("=== Reference Implementation: Claude Agent SDK ===")

    tp, lp, mp = setup_otel()

    anyio.run(run_agent_query_reference)
    anyio.run(run_plugin_skill_reference)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
