# Client Inference Time Per Output Chunk Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferencetime_per_output_chunk)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai], [openai-agents] |
| gen_ai.provider.name | [openai], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [openai-agents] |
| gen_ai.request.model | [openai], [openai-agents] |
| server.port | [openai], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [openai], [openai-agents] |
| gen_ai.response.service_tier | [openai], [openai-agents] |
| server.address | [openai], [openai-agents] |

[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
