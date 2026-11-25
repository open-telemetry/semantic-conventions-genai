# Client Inference Usage Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusageinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [google-genai], [groq], [ollama], [openai] |
| gen_ai.provider.name | [anthropic], [google-genai], [groq], [ollama], [openai] |
| gen_ai.token.modality | [anthropic], [google-genai], [groq], [ollama], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [google-genai], [groq], [ollama], [openai] |
| server.port | [anthropic], [groq], [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [google-genai], [groq], [ollama], [openai] |
| gen_ai.response.service_tier | [groq], [openai] |
| server.address | [anthropic], [groq], [ollama], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
