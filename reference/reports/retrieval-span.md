# Retrieval Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#retrievals)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [haystack], [langchain], [llamaindex] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.data_source.id | [haystack], [langchain], [llamaindex] |
| gen_ai.provider.name | [llamaindex] |
| gen_ai.request.model | [llamaindex] |
| server.port | [llamaindex] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.retrieval.top_k | [haystack], [langchain], [llamaindex] |
| server.address | [llamaindex] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.retrieval.documents | [haystack], [langchain], [llamaindex] |
| gen_ai.retrieval.query.text | [haystack], [langchain], [llamaindex] |

[haystack]: ../scenarios/haystack/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
