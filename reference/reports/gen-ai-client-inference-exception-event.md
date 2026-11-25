# Client Inference Exception Event

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#event-gen_aiclientinferenceexception)**

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
