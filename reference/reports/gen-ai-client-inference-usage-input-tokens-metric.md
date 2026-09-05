# Client Inference Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-inference-usage-metrics.md#metric-gen_aiclientinferenceusageinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [google-genai], [openai] |
| gen_ai.provider.name | [anthropic], [google-genai], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [google-genai], [openai] |
| server.port | [anthropic], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [google-genai], [openai] |
| server.address | [anthropic], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[openai]: ../scenarios/openai/scenario.py
