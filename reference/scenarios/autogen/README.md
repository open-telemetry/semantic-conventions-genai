# autogen

AutoGen is a multi-agent framework. It calls models through a chat-completion
client (e.g. `OpenAIChatCompletionClient`), so it **delegates inference** to the
underlying LLM library. It owns the agent, tool, and team (workflow) operations
it runs directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| create_agent | No — `create_agent` is a client op for remote agent services; AutoGen agents are local | ❌ Instrumented in error |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| execute_tool | Yes — AutoGen runs the tool | ✅ Implemented |
| invoke_workflow | Yes — team / group chat orchestration (e.g. `RoundRobinGroupChat`) | ❌ Not implemented |
