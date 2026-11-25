# Client Inference Reasoning Output Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusagereasoningoutput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-genai], [groq], [openai] |
| gen_ai.provider.name | [google-genai], [groq], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [google-genai], [groq], [openai] |
| server.port | [groq], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [google-genai], [groq], [openai] |
| gen_ai.response.service_tier | [openai] |
| server.address | [groq], [openai] |

[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai]: ../scenarios/openai/scenario.py
