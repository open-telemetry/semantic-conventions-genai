# Client Inference Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferenceduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [anthropic], [groq], [ollama] |
| gen_ai.provider.name | [agent-framework], [anthropic], [groq], [ollama] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [agent-framework], [anthropic], [groq], [ollama] |
| server.port | [anthropic], [groq], [ollama] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [agent-framework], [anthropic], [groq], [ollama] |
| server.address | [agent-framework], [anthropic], [groq], [ollama] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
[groq]: ../scenarios/groq/scenario.py
[ollama]: ../scenarios/ollama/scenario.py
