# external-ref

This scenario exercises an opaque external reference on both allow and block
paths through the OpenAI Agents SDK's input guardrail runtime. The SDK owns the
agent run and tool execution, while the underlying `openai` client owns inference.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` evaluates the input guardrail and invokes the agent | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |

The reference is returned by the guardrail in its `output_info` and copied onto the `invoke_agent` span on both runs.
