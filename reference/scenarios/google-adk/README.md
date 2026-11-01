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
| execution state changed event | Yes — `EventActions.state_delta` exposes runtime-owned deltas | ✅ Implemented (count only) |

The scenario also proves ADK's public resumability path with an `App` configured
for resumability, an in-memory session, and a confirmation-gated `FunctionTool`.
The first `Runner.run_async` invocation suspends when its event stream reports a
tool-confirmation request. A second call resumes the same ADK `invocation_id`
with the matching confirmed function response. The proof emits existing
workflow, agent, and owned tool spans, and records the
`EventActions.state_delta` produced when the confirmed tool updates
`ToolContext.state`. It uses `Event.invocation_id` only to verify that ADK
resumed the same execution; the identifier is not emitted. The event records
only the delta size, never application-controlled key names or state values. It does not record
messages, tool arguments or results, session state, or idempotency data for
this path.
