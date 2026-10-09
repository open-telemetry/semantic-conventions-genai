# google-adk

The Google Agent Development Kit (ADK) is an agent framework. It calls models
through its model layer (e.g. `google-genai`), so it **delegates inference**. It
owns the agent, workflow, tool, memory, and remote-agent operations it runs
directly.

The `RemoteA2aAgent` scenario exercises two library-owned caller paths:

- a `FunctionNode` calls public `Context.run_node` with a
  `RemoteA2aAgent`; `Context.node` identifies the workflow step and the
  `run_node` argument identifies the target;
- a `routing_agent` invokes a `RemoteA2aAgent` through `AgentTool`;
  `ToolContext.agent_name` identifies the caller and public `AgentTool.agent`
  identifies the target. The AgentTool invocation records an execute-tool
  transfer span, and the remote request records its invoke-agent CLIENT child.

Instrumentation carries the workflow call through a task-local context because
ADK schedules the target node in another task. It propagates the AgentTool call
through OpenTelemetry context. Both paths reach an injected public A2A
`ClientFactory`, which wraps public `Client.send_message` to create the CLIENT
span. Two workflow steps call the same remote-agent instance concurrently with
the AgentTool call. The scenario verifies that each CLIENT span keeps the
correct caller and remains a child of the matching local `RemoteA2aAgent`
execution. It does not use `RemoteA2aAgent.parent_agent`, private ADK state, or
span topology to infer the caller. ADK currently marks its A2A integration as
experimental.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model client (`google-genai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| invoke_agent (client) | Yes — `RemoteA2aAgent` invokes a remote A2A agent | ✅ Implemented |
| invoke_workflow | Yes — graph-based `Workflow` nodes | ✅ Implemented |
| execute_tool | Yes — ADK runs the tool | ✅ Implemented |
| memory | Yes — memory service upsert / search | ✅ Implemented |
| skills | Yes — `SkillToolset` runs the skill tools | ✅ Implemented |
