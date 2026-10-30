# Client Inference Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferenceduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [anthropic], [groq], [openai] |
| gen_ai.provider.name | [agent-framework], [anthropic], [groq], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [agent-framework], [anthropic], [groq], [openai] |
| server.port | [anthropic], [groq], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [agent-framework], [anthropic], [groq], [openai] |
| server.address | [agent-framework], [anthropic], [groq], [openai] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai]: ../scenarios/openai/scenario.py
