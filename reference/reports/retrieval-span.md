# Retrieval Span

> **[Semantic Convention](../../docs/gen-ai/retrieval.md#span-gen_airetrieval)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [haystack], [langchain], [llamaindex] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.retrieval.top_k | [haystack], [langchain], [llamaindex] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.retrieval.documents | [haystack], [langchain], [llamaindex] |
| gen_ai.retrieval.query.text | [haystack], [langchain], [llamaindex] |

[haystack]: ../scenarios/haystack/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
