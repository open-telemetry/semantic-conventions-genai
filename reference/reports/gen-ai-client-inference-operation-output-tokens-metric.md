# Client Inference Operation Output Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceoperationoutput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [azure-openai], [google-genai], [ollama], [openai] |
| gen_ai.provider.name | [anthropic], [azure-openai], [google-genai], [ollama], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [azure-openai], [google-genai], [ollama], [openai] |
| server.port | [anthropic], [azure-openai], [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [azure-openai], [google-genai], [ollama], [openai] |
| server.address | [anthropic], [azure-openai], [ollama], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
