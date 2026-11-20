# Client Inference Usage Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusageinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [google-genai], [ollama], [openai] |
| gen_ai.provider.name | [anthropic], [google-genai], [ollama], [openai] |
| gen_ai.token.modality | [anthropic], [google-genai], [ollama], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [google-genai], [ollama], [openai] |
| server.port | [anthropic], [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [google-genai], [ollama], [openai] |
| server.address | [anthropic], [ollama], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
