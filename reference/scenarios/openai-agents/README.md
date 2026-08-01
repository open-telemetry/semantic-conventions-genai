# openai-agents

The OpenAI Agents SDK orchestrates agents. It calls the model through the
`openai` client, so it **delegates inference**. It owns the agent run and tool
execution it drives directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` on an agent | ✅ Implemented |
| invoke_workflow | Yes — the SDK's tracing models a run as a workflow (`workflow_name`) | ❌ Not implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |