# openai-agents

The OpenAI Agents SDK orchestrates agents. It calls the model through the
`openai` client, so it **delegates inference**. It owns the agent run and tool
execution it drives directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the `openai` client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Runner.run` on an agent | ✅ Implemented |
| invoke_workflow | Yes — `Runner.run` coordinates agents through handoffs | ✅ Implemented |
| execute_tool | Yes — the SDK runs the function tool | ✅ Implemented |
| workflow inference/tool call counts | Yes — model, local-tool and handoff start hooks | ✅ Implemented |

The scenario covers a single agent with a tool and a two-agent handoff workflow.
The workflow counts calls before execution and records totals when the run ends,
including on failure. Provider-hosted tools do not trigger the local-tool hook.
