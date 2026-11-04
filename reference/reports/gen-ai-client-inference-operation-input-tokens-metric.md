# Client Inference Operation Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceoperationinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [azure-openai], [google-genai], [openai] |
| gen_ai.provider.name | [anthropic], [azure-openai], [google-genai], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [azure-openai], [google-genai], [openai] |
| server.port | [anthropic], [azure-openai], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [azure-openai], [google-genai], [openai] |
| server.address | [anthropic], [azure-openai], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[openai]: ../scenarios/openai/scenario.py
