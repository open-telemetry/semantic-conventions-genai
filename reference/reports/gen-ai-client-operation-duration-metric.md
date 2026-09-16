# Client Operation Duration Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [anthropic] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [agent-framework], [anthropic] |
| gen_ai.request.model | [agent-framework], [anthropic] |
| server.port | [anthropic] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [agent-framework], [anthropic] |
| server.address | [agent-framework], [anthropic] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
