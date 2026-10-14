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
| inference (`decision`) | Yes — `client.decisions.create` calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the base client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
| retrieval | Yes — Vector Stores search / `file_search` tool | ❌ Not implemented |
| memory | Yes — Conversations API / stored responses | ❌ Not implemented |

`scenario.py --scenario decisions` exercises the real OpenAI SDK against an in-process HTTP mock
transport using the documented Decisions response shape. It covers routing,
bounded scoring, predicates, typed choices, mixed answers with an explicit refusal,
and a request error.
These fixtures test SDK capturability, not model accuracy or live service behavior.

The scenario records one inference span and duration per request, and usage from
the returned SDK object. With capture enabled, it emits `gen_ai.decision.results`
as JSON on spans or structured data on an inference-detail event. Results preserve
question indices, selected option types, selected probabilities, and score scales.
Details events also include request usage. Failed requests emit a correlated
`gen_ai.client.operation.exception` event, even when result capture is disabled.
Capture is disabled by default. It does not emit full candidate lists,
distributions, generic confidence, prompt text, or invented finish reasons.
Tests also verify that default capture and opt-in result capture omit unsupported
system instructions, tool definitions, and generation parameters while retaining
model, provider, and usage attributes. Per-question instructions are not system
instructions.

Run `uv run python -m unittest discover -s . -p test_decisions.py -v` here to test
emitted content, event correlation, privacy defaults, refusal/error handling,
unknown answers, score scales, and the result schema.
