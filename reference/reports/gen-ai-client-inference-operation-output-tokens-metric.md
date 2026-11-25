# Client Inference Operation Output Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceoperationoutput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [azure-openai], [google-genai], [groq], [openai], [openai-agents] |
| gen_ai.provider.name | [anthropic], [azure-openai], [google-genai], [groq], [openai], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [openai-agents] |
| gen_ai.request.model | [anthropic], [azure-openai], [google-genai], [groq], [openai], [openai-agents] |
| server.port | [anthropic], [azure-openai], [groq], [openai], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [azure-openai], [google-genai], [groq], [openai], [openai-agents] |
| gen_ai.response.service_tier | [azure-openai], [groq], [openai], [openai-agents] |
| server.address | [anthropic], [azure-openai], [groq], [openai], [openai-agents] |

[anthropic]: ../scenarios/anthropic/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
