# Client Inference Reasoning Output Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusagereasoningoutput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-genai], [groq], [openai], [openai-agents] |
| gen_ai.provider.name | [google-genai], [groq], [openai], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [openai-agents] |
| gen_ai.request.model | [google-genai], [groq], [openai], [openai-agents] |
| server.port | [groq], [openai], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [google-genai], [groq], [openai], [openai-agents] |
| gen_ai.response.service_tier | [openai], [openai-agents] |
| server.address | [groq], [openai], [openai-agents] |

[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
