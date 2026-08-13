# aws-bedrock-agent

This scenario creates a **remote** AWS Bedrock Agent via the Bedrock Agent
`CreateAgent` API and invokes it via the Bedrock Agent Runtime `InvokeAgent`
API. The agent's reasoning, model calls, and tool execution all happen
server-side, across a process boundary that client instrumentation cannot
observe — so only the client `create_agent` and `invoke_agent` spans are owned
here. Everything else belongs to the remote agent service.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| create_agent | Yes — creates the remote agent | ✅ Implemented |
| invoke_agent (client) | Yes — invokes the remote agent | ✅ Implemented |
| inference (`chat`) | No — runs remotely inside the agent service | ✅ Correctly not emitted |
| execute_tool | No — runs remotely inside the agent service | ✅ Correctly not emitted |
