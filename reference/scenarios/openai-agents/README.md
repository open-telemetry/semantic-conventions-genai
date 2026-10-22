# openai-agents

The OpenAI Agents SDK orchestrates agents. It calls the model through the
`openai` client, so it **delegates inference**. It owns the agent run and tool
execution it drives directly, including the sandbox tools it ships.

Agent-as-tool calls use `execute_tool {gen_ai.tool.name}` span names and record
the SDK tool's target separately in `gen_ai.transfer.target.name`. Agent spans
wrap actual SDK runner calls, so argument validation failures do not create a
specialist invocation span.

Each agent records finish reasons from its own captured model responses and
token counts from its `RunResult.raw_responses`. The SDK shares context usage
between an agent tool and its caller, so that shared total would incorrectly
include the other agent's model calls.

The workflow also exercises native `handoff()`. Instrumentation wraps the
selected handoff's `on_invoke_handoff` at the SDK's `execute_handoffs` boundary,
where the source agent and function-tool call are available. The returned agent
provides the target name. The tool records `pass_control` and ends before the
target's SDK turn begins. Each agent's turn has its own `invoke_agent` span.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` on an agent | ✅ Implemented |
| invoke_workflow | Yes — the SDK's tracing models a run as a workflow (`workflow_name`) | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |
| execute_tool (command) | Yes — the `Shell` sandbox capability runs a general command through `exec_command` | ✅ Implemented |