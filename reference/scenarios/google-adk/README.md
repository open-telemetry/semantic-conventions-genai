# google-adk

The Google Agent Development Kit (ADK) is an agent framework. It calls models
through its model layer (e.g. `google-genai`), so it **delegates inference**. It
owns the agent, workflow, tool, memory, and remote-agent operations it runs
directly.

The `RemoteA2aAgent` scenario records its local ADK execution as an
`invoke_agent` INTERNAL span and the A2A request as its `invoke_agent` CLIENT
child. The scenario checks that relationship using the recorded span IDs. ADK
currently marks its A2A integration as experimental.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model client (`google-genai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| invoke_agent (client) | Yes — `RemoteA2aAgent` invokes a remote A2A agent | ✅ Implemented |
| invoke_workflow | Yes — workflow agents (e.g. `SequentialAgent`) | ✅ Implemented |
| execute_tool | Yes — ADK runs the tool | ✅ Implemented |
| memory | Yes — memory service upsert / search | ✅ Implemented |
