# openai-agents

The OpenAI Agents SDK orchestrates agents. It calls the model through the
`openai` client, so it **delegates inference**. It owns the agent run and tool
execution it drives directly, including the sandbox tools it ships.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` on an agent | ✅ Implemented |
| invoke_workflow | Yes — the SDK's tracing models a run as a workflow (`workflow_name`) | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |
| execute_tool (command) | Yes — the `Shell` sandbox capability runs a general command through `exec_command` | ✅ Implemented |