# openai

The `openai` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. It also owns retrieval
(the Vector Stores API — `client.vector_stores.search` — and the `file_search`
tool) and memory (the Conversations API and stored responses via `store` /
`previous_response_id`). It has no agent, workflow, or plan concepts (the
Assistants API is covered by the `openai-assistants` scenario).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ❌ Shown, but not instrumentable |
| retrieval | Yes — Vector Stores search / `file_search` tool | ❌ Not implemented |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |
