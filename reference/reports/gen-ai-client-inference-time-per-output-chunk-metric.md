# Client Inference Time Per Output Chunk Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferencetime_per_output_chunk)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [ollama], [openai] |
| gen_ai.provider.name | [ollama], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [ollama], [openai] |
| server.port | [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [ollama], [openai] |
| gen_ai.response.service_tier | [openai] |
| server.address | [ollama], [openai] |

[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
