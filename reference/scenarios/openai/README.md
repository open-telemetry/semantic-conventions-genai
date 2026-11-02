# openai

The `openai` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. It also owns retrieval
(the Vector Stores API — `client.vector_stores.search` — and the `file_search`
tool) and memory (the Conversations API and stored responses via `store` /
`previous_response_id`). It has no agent, workflow, or plan concepts (the
Assistants API is covered by the `openai-assistants` scenario).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented, including streaming TTFC |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| fetch_response | Yes — Responses API `client.responses.retrieve` | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | Yes — Vector Stores search / `file_search` tool | ❌ Not implemented |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

Streaming TTFC is recorded on the span and metric at the first non-empty text, refusal, audio data/transcript, or function-call name/argument delta. Role, ID, usage, and empty deltas do not stop the timer.

The scenario also checks metadata filtering, non-text output, authentication, retry backoff, and streams with no output using the real SDK, mock HTTP responses, and a controlled clock. These assertions run through the existing `run-scenario openai --strict` entry point.

Embeddings covers successful requests and an SDK error from a mock HTTP response.
Failed requests record duration and zero input tokens with `error.type`.
The SDK `BadRequestError` also produces a correlated
`gen_ai.client.embeddings.exception` WARN log with SDK exception details.

Inference also covers an SDK `RateLimitError` from a mock HTTP response, recorded
as a correlated `gen_ai.client.inference.exception` WARN log with SDK exception details.

Fetch response also covers an SDK `NotFoundError` from a mock HTTP response,
recorded as a correlated `gen_ai.client.fetch_response.exception` WARN log with SDK exception details.
A successfully fetched response whose original generation failed does not produce this event.
