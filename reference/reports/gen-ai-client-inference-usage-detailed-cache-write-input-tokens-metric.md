# Client Inference Detailed Cache Write Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-inference-usage-metrics.md#metric-gen_aiclientinferenceusagedetailedcache_writeinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [openai] |
| gen_ai.provider.name | [anthropic], [openai] |
| gen_ai.token.modality | [anthropic], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [anthropic], [openai] |
| server.port | [anthropic], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [openai] |
| server.address | [anthropic], [openai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[openai]: ../scenarios/openai/scenario.py
