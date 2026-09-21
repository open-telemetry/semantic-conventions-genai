# claude-agent-sdk-guardrail reference scenario

Reference implementation mapping a **Claude Code / Claude Agent SDK
`PreToolUse` hook** onto the base `run_guardrail` span.

## What it demonstrates

A `PreToolUse` hook sees a proposed tool call before it runs and returns
allow/deny. That is a guardrail evaluation whose target is the tool call on the
input side. The hook is the instrumentation seam: it emits one
`gen_ai.run_guardrail.internal` span per evaluation, deriving each attribute
from the hook input the SDK hands it at runtime.

| Attribute | Source at the `PreToolUse` hook boundary |
| --- | --- |
| `gen_ai.operation.name` | `run_guardrail` (constant) |
| `gen_ai.guardrail.component.name` | the hook (`Claude Code PreToolUse hook`) |
| `gen_ai.guardrail.target.type` | `input` (pre-tool evaluation) |
| `gen_ai.guardrail.target.subtype` | `tool_call` |
| `gen_ai.guardrail.target.id` | `tool_use_id` from the hook input |
| `gen_ai.guardrail.verdict.type` | `deny` if the command trips the policy else `allow` |
| `gen_ai.guardrail.action.type` | `block` when denied (the SDK stops the tool) else `allow` |
| `gen_ai.guardrail.verdict.reason` | policy explanation on deny |
| `gen_ai.guardrail.security.risk.category` | `excessive_agency` (OWASP LLM06) on deny |

The scenario registers a real hook via `ClaudeAgentOptions.hooks` and drives it
with a mock CLI (`mock_cli.py`) that proposes a destructive `Bash` command
(`rm -rf ...`). The hook denies it, so the SDK does not execute the tool.

## Why streaming mode

Hooks are registered during the control-protocol `initialize` handshake, which
only runs in **streaming** mode. `query(prompt=str)` is one-shot and never
initializes hooks, so this scenario uses `ClaudeSDKClient` (bidirectional).

## Mock CLI control protocol

`mock_cli.py` speaks the JSON-line control protocol from
`claude_agent_sdk/_internal/query.py`:

1. SDK -> CLI `control_request {subtype: initialize, hooks: {...}}` — the mock
   captures the PreToolUse `hookCallbackIds` and acks.
2. SDK -> CLI `{type: user}` — the mock emits an assistant `tool_use` (Bash)
   block and sends a `hook_callback` control request back to the SDK.
3. CLI -> SDK `control_request {subtype: hook_callback, callback_id, input}` —
   the SDK runs the Python hook (the guardrail span is emitted here).
4. SDK -> CLI `control_response {response: {hookSpecificOutput:
   {permissionDecision: "deny"}}}` — the mock emits a blocked `tool_result` and
   the final `result`.

## Status

Scaffold authored from SDK source (claude-agent-sdk 0.2.149); **not yet run
end to end** — the work laptop cannot reach public PyPI to install the SDK.
Validate on a machine with the real SDK installed:

```bash
cd reference
uv run run-scenario claude-agent-sdk-guardrail
uv run update-reports
```
