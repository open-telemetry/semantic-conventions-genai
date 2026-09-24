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

## Capture limitation

The scenario's own guardrail creates the reference values and the `record_ref`
dictionary key. The SDK exposes `GuardrailFunctionOutput.output_info` as arbitrary
output information; it does not define that key or its record semantics.
Generic SDK instrumentation therefore cannot infer an external record reference
from this example without an application-specific mapping.

The emitted attribute demonstrates the proposed join shape, not native SDK
support for `gen_ai.external_ref`. The example also does not exercise a stored
record or demonstrate that its referent remains stable. A real producer's
runtime record identifier is still needed to substantiate this convention.
