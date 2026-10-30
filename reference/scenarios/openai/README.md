# openai

The `openai` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. It also owns memory (the Conversations
API and stored responses via `store` / `previous_response_id`). It has no agent, workflow, or plan concepts (the
Assistants API is covered by the `openai-assistants` scenario).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented, including streaming TTFC |
| inference exception | Yes, the SDK raises exceptions for failed inference calls | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | No - Vector Stores search is a search service call, not GenAI retrieval; `file_search` runs server-side | ✅ Correctly not emitted |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

Streaming TTFC is recorded on the span and metric at the first non-empty text, refusal, audio data/transcript, or function-call name/argument delta. Role, ID, usage, and empty deltas do not stop the timer.

The scenario also checks metadata filtering, non-text output, authentication, retry backoff, and streams with no output using the real SDK, mock HTTP responses, and a controlled clock. These assertions run through the existing `run-scenario openai --strict` entry point.

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
