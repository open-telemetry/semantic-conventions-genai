"""Reference implementation: Claude Code PreToolUse hook as a GenAI guardrail.

A Claude Code / Claude Agent SDK ``PreToolUse`` hook sees a proposed tool call
before it runs and returns allow/deny. That maps directly onto a GenAI
``run_guardrail`` evaluation whose target is the tool call (input side).

This scenario registers a real PreToolUse hook via ClaudeAgentOptions.hooks and
drives it with a mock CLI (mock_cli.py) that proposes a destructive Bash
command. The hook is the instrumentation seam: inside it we emit a
``run_guardrail`` internal span describing the guardrail's verdict (deny) and
the enforced action (block), then return the deny decision to the SDK.

Hooks only fire in streaming mode, so this uses ClaudeSDKClient rather than the
one-shot query(prompt=str) path.

Validate on a machine with the real claude-agent-sdk==0.2.149 (public PyPI):
    cd reference && uv run run-scenario claude-agent-sdk-guardrail
"""

import os

from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_CLI_PATH = os.path.join(
    _SCRIPT_DIR,
    "mock_cli.cmd" if os.name == "nt" else "mock_cli.py",
)

_reference_tracer = reference_tracer()

# Human-readable name of the guardrail component doing the evaluation.
GUARDRAIL_COMPONENT = "Claude Code PreToolUse hook"
# Simple deny policy: destructive shell verbs the guardrail refuses to run.
_DENY_MARKERS = ("rm -rf", "mkfs", "dd if=", ":(){", "shutdown", "reboot")


def _evaluate_command(command: str) -> tuple[str, str]:
    """Return (verdict, reason) for a proposed Bash command."""
    lowered = command.lower()
    for marker in _DENY_MARKERS:
        if marker in lowered:
            return "deny", "Destructive shell command blocked by policy"
    return "allow", ""


async def _guardrail_hook(input_data, tool_use_id, context):
    """PreToolUse hook: evaluate the tool call and emit a run_guardrail span."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {}) or {}
    command = tool_input.get("command", "")
    target_id = input_data.get("tool_use_id") or tool_use_id or ""

    verdict, reason = _evaluate_command(command)
    action = "block" if verdict == "deny" else "allow"

    span_name = f"run_guardrail {GUARDRAIL_COMPONENT}"
    attributes = {
        "gen_ai.operation.name": "run_guardrail",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.guardrail.component.name": GUARDRAIL_COMPONENT,
        "gen_ai.guardrail.verdict.type": verdict,
        "gen_ai.guardrail.action.type": action,
        "gen_ai.guardrail.target.type": "input",
        "gen_ai.guardrail.target.subtype": "tool_call",
        "gen_ai.guardrail.target.id": target_id,
    }
    with _reference_tracer.start_as_current_span(span_name, attributes=attributes) as span:
        if verdict != "allow":
            span.set_attribute("gen_ai.guardrail.verdict.reason", reason)
            # Security overlay: a destructive tool call maps to excessive agency.
            span.set_attribute("gen_ai.guardrail.security.risk.category", "excessive_agency")
        print(f"    -> guardrail {verdict} for {tool_name}: {reason or 'ok'}")

    if verdict == "deny":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


async def run_pretooluse_guardrail_reference():
    """Scenario: PreToolUse hook denies a destructive tool call (run_guardrail)."""
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        HookMatcher,
    )

    print("  [pretooluse_guardrail] PreToolUse hook as guardrail (reference impl)")

    if os.name != "nt":
        os.chmod(MOCK_CLI_PATH, os.stat(MOCK_CLI_PATH).st_mode | 0o111)
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"

    options = ClaudeAgentOptions(
        cli_path=MOCK_CLI_PATH,
        max_turns=1,
        permission_mode="default",
        hooks={
            "PreToolUse": [HookMatcher(matcher="Bash", hooks=[_guardrail_hook])],
        },
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Please delete my old data directory.")
        async for message in client.receive_response():
            _ = message


def main():
    import anyio

    print("=== Reference Implementation: Claude Agent SDK PreToolUse guardrail ===")

    tp, lp, mp = setup_otel()

    anyio.run(run_pretooluse_guardrail_reference)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
