# agent-governance

This scenario exercises the OpenAI Agents SDK's input guardrail runtime on both
allow and block paths. The SDK owns the agent run and tool execution, while the
underlying `openai` client owns inference.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` evaluates the input guardrail and invokes the agent | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |

`gen_ai.agent.governance.ref` is not emitted because its decision-operation
attachment point is not defined yet. The scenario demonstrates the SDK-owned
guardrail boundary without copying the attribute onto the surrounding agent
span.
