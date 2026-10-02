# google-adk

The Google Agent Development Kit (ADK) is an agent framework. It calls models
through its model layer (e.g. `google-genai`), so it **delegates inference**. It
owns the agent, workflow, tool, memory, and remote-agent operations it runs
directly.

The `RemoteA2aAgent` scenario exercises two library-owned caller paths:

- a `Workflow` graph directly schedules a `RemoteA2aAgent` node, whose execution
  context exposes the parent workflow node and remote target together;
- a `routing_agent` invokes another `RemoteA2aAgent` through `AgentTool`, whose
  tool context exposes the executing agent and configured remote target.

Instrumentation propagates those per-invocation values through OpenTelemetry
context to the lower-level A2A `send_message` call, where the CLIENT span is
created. Both paths run concurrently, and the scenario verifies that each
CLIENT span retains the correct workflow or agent caller and remains a child of
the corresponding local `RemoteA2aAgent` execution. It does not use
`RemoteA2aAgent.parent_agent` or infer caller identity from span topology. ADK
currently marks its A2A integration as experimental.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model client (`google-genai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| invoke_agent (client) | Yes — `RemoteA2aAgent` invokes a remote A2A agent | ✅ Implemented |
| invoke_workflow | Yes — graph-based `Workflow` nodes | ✅ Implemented |
| execute_tool | Yes — ADK runs the tool | ✅ Implemented |
| memory | Yes — memory service upsert / search | ✅ Implemented |
| skills | Yes — `SkillToolset` runs the skill tools | ✅ Implemented |
