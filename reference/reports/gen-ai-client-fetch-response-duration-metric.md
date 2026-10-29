# Client Fetch Response Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-fetch-response.md#metric-gen_aiclientfetch_responseduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai] |
| gen_ai.provider.name | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| server.port | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [openai] |
| gen_ai.response.status | [openai] |
| server.address | [openai] |

[openai]: ../scenarios/openai/scenario.py
