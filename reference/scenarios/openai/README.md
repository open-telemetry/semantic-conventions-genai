# openai

The `openai` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. It also owns memory (the Conversations
API and stored responses via `store` / `previous_response_id`). It has no agent, workflow, or plan concepts (the
Assistants API is covered by the `openai-assistants` scenario).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented, including streaming TTFC, output-chunk intervals, and structured-output failures |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| fetch_response | Yes — Responses API `client.responses.retrieve` | ✅ Implemented, including function and built-in tool definitions |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | No - Vector Stores search is a search service call, not GenAI retrieval; `file_search` runs server-side | ✅ Correctly not emitted |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

The Chat Completions scenario checks that both streaming timing measurements count text and non-text output, including audio without a transcript. It also checks that metadata-only events don't reset the interval and that streams with fewer than two output chunks record no interval.

The scenario also checks authentication and retry backoff. These checks run through `run-scenario openai --strict` against the real SDK with mock HTTP responses and a controlled clock.

The scenario assumes content capture is enabled. Tool definitions include
descriptions and parameter schemas from the SDK's `tools` argument.

Embeddings exercises the SDK's `BadRequestError` from
`client.embeddings.create` using a mock HTTP 400 response. The error handler
records a correlated `gen_ai.client.embeddings.exception` WARN log and re-raises
the exception. Failed requests record duration and zero input tokens with
`error.type`.

Inference exercises the SDK's `RateLimitError` from
`client.chat.completions.create` using a mock HTTP 429 response, and an `APIError`
from a streamed response. Both errors emit a correlated
`gen_ai.client.inference.exception` WARN log and propagate to the caller.
When the stream reports usage before it fails, the usage counters carry the
same `error.type` as the span.
Closing a stream without an error does not emit this log.

Fetch spans record the built-in `web_search` tool with type `openai.web_search`
and name `web_search`. They record `gen_ai.tool.definitions` as `[]` when the
stored response includes an empty tool list and omit the attribute when the
response doesn't provide a list.

Fetch response exercises the SDK's `NotFoundError` from
`client.responses.retrieve` using a mock HTTP 404 response. The error handler
records a correlated `gen_ai.client.fetch_response.exception` WARN log and
re-raises the exception.
