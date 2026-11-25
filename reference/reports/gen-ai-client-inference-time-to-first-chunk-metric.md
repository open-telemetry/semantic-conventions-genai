# Client Inference Time To First Chunk Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferencetime_to_first_chunk)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [openai] |
| gen_ai.provider.name | [anthropic], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [openai] |
| server.port | [anthropic], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [openai] |
| gen_ai.response.service_tier | [openai] |
| server.address | [anthropic], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[openai]: ../scenarios/openai/scenario.py
