# mistralai

The `mistralai` client is a **model-call boundary**: it calls the model
directly, so it owns inference and embeddings. Tool calling is supported, with
the tool itself running in application code.

The same client also drives Mistral's hosted **Agents** and **Workflows**
services, which run server-side. The client owns the create-agent and
invoke-agent client operations; the agent's reasoning, model calls, and tool
execution happen across a process boundary it cannot observe.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| create_agent | Yes — hosted Agents API `beta.agents.create` | ✅ Implemented |
| invoke_agent (client) | Yes — `beta.conversations.start` runs the remote agent | ❌ Not implemented |
| invoke_workflow | Yes — hosted Workflows API | ❌ Not implemented |
