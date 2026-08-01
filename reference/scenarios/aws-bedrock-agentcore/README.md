# aws-bedrock-agentcore

This scenario covers the **AWS Bedrock AgentCore Memory** service. The client
owns the memory operations it performs directly — creating and deleting memory
stores, and creating, updating, searching, and deleting memory records. The
AgentCore Runtime that hosts agents is a separate, remote service.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| memory | Yes — AgentCore Memory store / record create, update, search, delete | ✅ Implemented |
| invoke_agent (client) | No — AgentCore Runtime runs agents remotely (separate service) | ✅ Correctly not emitted |
