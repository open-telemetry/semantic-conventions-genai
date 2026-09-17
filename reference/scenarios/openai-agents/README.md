# openai-agents

The OpenAI Agents SDK orchestrates agents. It calls the model through the
`openai` client, so it **delegates inference**. It owns the agent run and tool
execution it drives directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` on an agent | ✅ Implemented |
| invoke_workflow | Yes — the SDK's tracing models a run as a workflow (`workflow_name`) | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |

The scenario covers three runs: a single agent with a tool, a two-agent handoff
under one workflow, and a workflow nested inside another workflow. The
single-agent run records the agent grain only. The handoff run records the
workflow grain only, because its single `Runner.run` passes through two agents
and the SDK's per-run totals belong to no single agent. The nested run records
both grains, so the enclosing workflow's counts can be checked against the
agent counts.
