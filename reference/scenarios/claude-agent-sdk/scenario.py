"""Reference implementation for Claude Agent SDK."""

import json
import os

from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_CLI_PATH = os.path.join(
    _SCRIPT_DIR,
    "mock_cli.cmd" if os.name == "nt" else "mock_cli.py",
)

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
    with _reference_tracer.start_as_current_span("chat claude", attributes=span_attributes) as span:
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


async def run_tool_permission_denial_gap():
    """Probe Claude Agent SDK permission denial over its real control channel."""
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        PermissionResultDeny,
        ResultMessage,
        query,
    )

    print("  [permission_denial_gap] Claude SDK can_use_tool denies before execution")

    if os.name != "nt":
        os.chmod(MOCK_CLI_PATH, os.stat(MOCK_CLI_PATH).st_mode | 0o111)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"

    seen = {}

    async def deny_tool(tool_name, input_data, context):
        seen["tool_name"] = tool_name
        seen["input"] = dict(input_data)
        seen["tool_use_id"] = context.tool_use_id
        seen["decision_reason"] = context.decision_reason
        attributes = {
            "gen_ai.tool.call.decision.outcome": "deny",
            "gen_ai.tool.name": tool_name,
        }
        if context.tool_use_id:
            attributes["gen_ai.tool.call.id"] = context.tool_use_id
        reference_event_logger("gen_ai.reference.claude_agent_sdk").emit(
            event_name="gen_ai.tool.call.decision",
            body="Tool call denied",
            attributes=attributes,
        )
        return PermissionResultDeny(
            message="Denied by the permission-probe policy.",
            interrupt=False,
        )

    options = ClaudeAgentOptions(
        cli_path=MOCK_CLI_PATH,
        max_turns=1,
        can_use_tool=deny_tool,
    )

    saw_result = False
    async for message in query(
        prompt="[permission-probe] run the protected Bash command",
        options=options,
    ):
        if isinstance(message, ResultMessage):
            saw_result = True

    if not saw_result:
        raise RuntimeError("Claude permission probe did not reach a result frame.")
    if seen.get("tool_name") != "Bash":
        raise AssertionError(f"Unexpected permission tool: {seen!r}")
    if seen.get("tool_use_id") != "toolu_mock_permission_001":
        raise AssertionError(f"Missing stable permission tool_use_id: {seen!r}")

    print("    -> deny returned for Bash tool_use_id=toolu_mock_permission_001")


def main():
    import anyio

    print("=== Reference Implementation: Claude Agent SDK ===")

    tp, lp, mp = setup_otel()

    anyio.run(run_agent_query_reference)
    anyio.run(run_tool_permission_denial_gap)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
