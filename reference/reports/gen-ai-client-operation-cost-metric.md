# Client Operation Cost Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationcost)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [litellm] |
| gen_ai.provider.name | [litellm] |
| gen_ai.usage.cost.currency | [litellm] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [litellm] |
| server.port | [litellm] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [litellm] |
| gen_ai.usage.cost.source | [litellm] |
| server.address | [litellm] |

[litellm]: ../scenarios/litellm/scenario.py
