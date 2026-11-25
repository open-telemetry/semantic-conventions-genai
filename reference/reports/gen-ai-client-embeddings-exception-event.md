# Client Embeddings Exception Event

> **[Semantic Convention](../../docs/gen-ai/client-embeddings.md#event-gen_aiclientembeddingsexception)**

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| exception.message | [ollama], [openai] |
| exception.type | [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| exception.stacktrace | [ollama], [openai] |

[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
