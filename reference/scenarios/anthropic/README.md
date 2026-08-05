# anthropic

The `anthropic` client is a **model-call boundary**: it calls the Messages API
directly, so it owns inference. The API has no embeddings endpoint (Anthropic
points users to third-party embedding providers), so embeddings is out of scope.
Tool use is supported, but the tool itself runs in application code.

The same client also drives the **Managed Agents** service (`beta.agents`,
`beta.sessions`, `beta.memory_stores`), where agents run server-side. The client
owns the create-agent and invoke-agent client operations; the agent's reasoning,
model calls, and tool execution happen across a process boundary it cannot
observe.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — Messages API, calls the model directly | ✅ Implemented |
| execute_tool | No — the Messages API returns tool-use requests but doesn't execute tools; the tool runs in app code | ➖ Not instrumentable |
| create_agent | Yes — Managed Agents `beta.agents.create` | ✅ Implemented |
| invoke_agent (client) | Yes — a Managed Agents session runs the remote agent | ❌ Not implemented |
| memory | Yes — Managed Agents memory stores | ❌ Not implemented |

`invoke_agent` needs care: `beta.sessions.events.send` only queues the user
event and returns the accepted events. The agent then runs asynchronously (the
session reports `running`) and its output arrives over
`beta.sessions.events.stream`, so output messages and usage are not available
when the send call returns.
