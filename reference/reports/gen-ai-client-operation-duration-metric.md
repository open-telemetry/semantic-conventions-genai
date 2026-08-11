# Client Operation Duration Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [adk_a2a], [agent-framework], [anthropic] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [adk_a2a], [agent-framework], [anthropic] |
| gen_ai.request.model | [adk_a2a], [agent-framework], [anthropic] |
| server.port | [anthropic] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [adk_a2a], [agent-framework], [anthropic] |
| server.address | [agent-framework], [anthropic] |

[adk_a2a]: ../scenarios/adk_a2a/scenario.py
[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
