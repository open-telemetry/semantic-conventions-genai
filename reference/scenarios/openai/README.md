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

The streaming Chat Completions scenario records time to first chunk from before
the SDK call (including internal retries) and intervals between output-bearing
events. Text, refusals, audio data/transcripts, and tool-call name/argument deltas
count; role/ID-only, usage-only, finish-only, and audio-expiry-only updates do not.
Multiple choices in one event count once. Values come from decoded SDK responses
and a monotonic client clock, independently of message-content capture.

Run the deterministic streaming tests with:

```sh
uv run --frozen --project reference/scenarios/openai python reference/scenarios/openai/test_streaming.py
```

The tests use the real SDK with a mock HTTP transport and verify retry-inclusive
timing, excluded events between chunks, multiple choices, audio, tool calls,
empty/single-chunk streams, and interrupted streams without calling a model.
