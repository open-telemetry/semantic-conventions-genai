# Server Time To First Token Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiservertime_to_first_token)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [transformers] |
| gen_ai.provider.name | [transformers] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [transformers] |
| server.port | (none) |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | (none) |
| server.address | (none) |

[transformers]: ../scenarios/transformers/scenario.py
