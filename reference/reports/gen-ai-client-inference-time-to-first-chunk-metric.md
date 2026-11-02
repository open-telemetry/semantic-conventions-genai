# Client Inference Time to First Chunk Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferencetime_to_first_chunk)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai], [pydantic-ai] |
| gen_ai.provider.name | [openai], [pydantic-ai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [openai], [pydantic-ai] |
| server.port | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [openai], [pydantic-ai] |
| server.address | [openai] |

[openai]: ../scenarios/openai/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
