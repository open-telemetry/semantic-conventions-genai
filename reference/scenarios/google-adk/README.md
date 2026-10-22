# google-adk

The Google Agent Development Kit (ADK) is an agent framework. It calls models
through its model layer (e.g. `google-genai`), so it **delegates inference**. It
owns the agent, workflow, tool, and memory operations it runs directly.

The agent-as-tool scenario records the caller's session ID on the tool span.
The specialist span wraps ADK's actual agent execution, after tool argument
validation. Both agents record finish reasons and accumulated token usage from
their own ADK events, filtered by `event.author`.

The native handoff scenario registers `sub_agents` and instruments
`TransferToAgentTool.run_async`. The caller comes from `ToolContext.agent_name`,
and the target comes from `ToolContext.actions.transfer_to_agent` after the
tool executes. The transfer records `pass_control`; the target's separate
`BaseAgent.run_async` span starts after the transfer tool returns.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model client (`google-genai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| invoke_workflow | Yes — workflow agents (e.g. `SequentialAgent`) | ✅ Implemented |
| execute_tool | Yes — ADK runs the tool | ✅ Implemented |
| memory | Yes — memory service upsert / search | ✅ Implemented |
| skills | Yes — `SkillToolset` runs the skill tools | ✅ Implemented |
