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
| inference exception | Yes, the SDK raises exceptions for failed inference calls | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | Yes — Vector Stores search / `file_search` tool | ❌ Not implemented |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

Embeddings covers successful requests and an SDK error from a mock HTTP response.
Failed requests record duration and zero input tokens with `error.type`.

Inference covers a successful call and an SDK `RateLimitError` from a mock HTTP
response. The failed call emits `gen_ai.client.inference.exception` as a WARN log
correlated with the inference span, with exception details from the SDK and the
same `error.type` on the span and duration metric. Exception events do not copy
prompt or completion content.

Run the inference exception regressions, including transport errors and a
successful SDK retry, with `uv run --frozen python -m unittest test_scenario`
from this directory.
