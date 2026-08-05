# azure-ai-foundry

This scenario uses the **Azure AI Foundry Agent Service**, which creates and
runs agents remotely. The client owns the create-agent and invoke-agent client
operations; the agent's reasoning, model calls, and tool execution all happen
server-side, across a process boundary the client cannot observe.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| create_agent | Yes — creates the remote agent | ✅ Implemented |
| invoke_agent (client) | Yes — runs the remote agent | ✅ Implemented |
| inference (`chat`) | No — runs remotely inside the agent service | ✅ Correctly not emitted |
| execute_tool | No — runs remotely inside the agent service | ✅ Correctly not emitted |
