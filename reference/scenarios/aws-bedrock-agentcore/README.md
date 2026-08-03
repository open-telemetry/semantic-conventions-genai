# aws-bedrock-agentcore

AWS Bedrock AgentCore is a suite of services (Memory, Runtime, Gateway,
built-in tools). This scenario currently covers only **AgentCore Memory** — the
client owns the memory operations it performs directly: creating and deleting
memory stores, and creating, updating, searching, and deleting memory records.

The same boto3 clients also reach the rest of the suite. Those calls run
server-side, but the client is the one making them, so they are instrumentable
here as client spans — the same way `aws-bedrock-agent` instruments
`InvokeAgent`.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| memory | Yes — AgentCore Memory store / record create, update, search, delete | ✅ Implemented |
| invoke_agent (client) | Yes — `InvokeAgentRuntime` invokes the remote agent | ❌ Not implemented |
| create_agent | No — `CreateAgentRuntime` deploys a container, not an agent configuration | ➖ Out of scope |
| execute_tool | Yes — `InvokeCodeInterpreter` / `InvokeBrowser` built-in tools | ❌ Not implemented |
| inference (`chat`) | No — runs remotely inside the agent runtime | ✅ Correctly not emitted |
