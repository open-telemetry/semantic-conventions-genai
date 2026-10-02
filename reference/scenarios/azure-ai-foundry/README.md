# azure-ai-foundry

This scenario uses `azure-ai-projects` to create and invoke a remote Microsoft
Foundry agent. Invocation goes through an agent-scoped OpenAI Responses client
and a Foundry conversation.

Foundry performs the agent's model calls, tool execution, state management, and
orchestration remotely. The client scenario instruments the create-agent and
invoke-agent boundaries, not the hidden server-side inference or tool spans.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| create_agent | Yes — creates the remote agent | ✅ Implemented |
| invoke_agent (client) | Yes — runs the remote agent | ✅ Implemented |
| inference (`chat`) | No — runs remotely inside the agent service | ✅ Correctly not emitted |
| execute_tool | No — runs remotely inside the agent service | ✅ Correctly not emitted |
