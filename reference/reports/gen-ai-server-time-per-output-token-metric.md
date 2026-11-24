# Server Time Per Output Token Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-metrics.md#metric-gen_aiservertime_per_output_token)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [transformers] |
| gen_ai.provider.name | [transformers] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [transformers] |
| server.port | [transformers] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [transformers] |
| server.address | [transformers] |

[transformers]: ../scenarios/transformers/scenario.py
