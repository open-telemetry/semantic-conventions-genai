# pydantic-ai

Pydantic AI is an agent framework. It calls the model through a model provider,
so it **delegates inference**. It owns the agent run and tool execution it
drives directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model provider (e.g. `openai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — `Agent.run` | ✅ Implemented |
| execute_tool | Yes — the agent runs the tool | ✅ Implemented |
