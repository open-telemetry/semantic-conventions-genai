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
transport using the full predicate request/response example from the
[OpenAI API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create).
The [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
publishes choice and score as answer excerpts; tests parse those excerpts with
the SDK answer models and run them through the same normalization function. They
do not add a synthetic response envelope. OpenAI documents the refusal variant
and partial-refusal behavior but does not show a literal refusal payload; its
test covers the documented response shape. The HTTP mock uses a placeholder
SDK key and makes no network call.

The same test module maps raw response JSON copied from TypeSafe's documented
[Noul](https://docs.typesafe.ai/primitives/noul),
[Choice](https://docs.typesafe.ai/primitives/choice), and
[Score](https://docs.typesafe.ai/primitives/score) examples into normalized
results, then validates them against both the JSON Schema and Pydantic model.
This is mocked contract validation: it does not run the TypeSafe SDK or contact
Jev. These fixtures test mapping and schema compatibility, not model accuracy or
live provider integration.

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
unknown answers, score scales, and the result schema. TypeSafe's documented Box
answer returns bounding-box coordinates, which are outside the current result
schema and are recorded as a coverage gap rather than coerced into another type.
