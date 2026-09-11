# Client Operation Duration Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [anthropic], [groq] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [agent-framework], [anthropic], [groq] |
| gen_ai.request.model | [agent-framework], [anthropic], [groq] |
| server.port | [anthropic], [groq] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [agent-framework], [anthropic], [groq] |
| server.address | [agent-framework], [anthropic], [groq] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
[groq]: ../scenarios/groq/scenario.py
