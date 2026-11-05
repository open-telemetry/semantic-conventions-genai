# openai

The `openai` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. It also owns memory (the Conversations
API and stored responses via `store` / `previous_response_id`). It has no agent, workflow, or plan concepts (the
Assistants API is covered by the `openai-assistants` scenario).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented, including streaming TTFC |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| fetch_response | Yes — Responses API `client.responses.retrieve` | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | No - Vector Stores search is a search service call, not GenAI retrieval; `file_search` runs server-side | ✅ Correctly not emitted |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

Streaming TTFC is recorded on the span and metric at the first non-empty text, refusal, audio data/transcript, or function-call name/argument delta. Role, ID, usage, and empty deltas do not stop the timer.

The scenario also checks metadata filtering, non-text output, authentication, retry backoff, and streams with no output using the real SDK, mock HTTP responses, and a controlled clock. These assertions run through the existing `run-scenario openai --strict` entry point.

Embeddings exercises the SDK's `BadRequestError` from
`client.embeddings.create` using a mock HTTP 400 response. The error handler
records a correlated `gen_ai.client.embeddings.exception` WARN log and re-raises
the exception. Failed requests record duration and zero input tokens with
`error.type`.

Inference exercises the SDK's `RateLimitError` from
`client.chat.completions.create` using a mock HTTP 429 response. The error handler
records a correlated `gen_ai.client.inference.exception` WARN log and re-raises
the exception.

Fetch response exercises the SDK's `NotFoundError` from
`client.responses.retrieve` using a mock HTTP 404 response. The error handler
records a correlated `gen_ai.client.fetch_response.exception` WARN log and
re-raises the exception.
