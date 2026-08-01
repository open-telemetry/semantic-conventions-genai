# aws-bedrock-agent

This scenario invokes a **remote** AWS Bedrock Agent via the Bedrock Agent
Runtime `InvokeAgent` API. The agent's reasoning, model calls, and tool
execution all happen server-side, across a process boundary that client
instrumentation cannot observe — so only the client `invoke_agent` span is
owned here. Everything else belongs to the remote agent service.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| create_agent (client) | Yes — creates the remote agent | ❌ Not implemented |
| invoke_agent (client) | Yes — invokes the remote agent | ✅ Implemented |
| inference (`chat`) | No — runs remotely inside the agent service | ✅ Correctly not emitted |
| execute_tool | No — runs remotely inside the agent service | ✅ Correctly not emitted |
