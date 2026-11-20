# Client Inference Usage Output Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusageoutput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [google-genai], [groq], [openai] |
| gen_ai.provider.name | [anthropic], [google-genai], [groq], [openai] |
| gen_ai.token.modality | [anthropic], [google-genai], [groq], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [google-genai], [groq], [openai] |
| server.port | [anthropic], [groq], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [google-genai], [groq], [openai] |
| server.address | [anthropic], [groq], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai]: ../scenarios/openai/scenario.py
