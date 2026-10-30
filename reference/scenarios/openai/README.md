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
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | Yes — Vector Stores search / `file_search` tool | ❌ Not implemented |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

Embeddings covers successful requests and an SDK error from a mock HTTP response.
Failed requests record duration and zero input tokens with `error.type`.
The SDK exception produces a `gen_ai.client.embeddings.exception` log with WARN
severity, correlated with the failed embeddings span. Its type, message, and
stacktrace come from the SDK exception.

Run the focused exception tests with `uv run --frozen python -m unittest test_embeddings_exceptions`.
They cover failed requests, successful requests, and successful SDK retries.
