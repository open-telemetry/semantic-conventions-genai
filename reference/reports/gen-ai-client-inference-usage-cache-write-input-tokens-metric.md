# Client Inference Cache Write Input Tokens Metric

> **[Semantic Convention](../../docs/gen-ai/gen-ai-token-metrics.md#metric-gen_aiclientinferenceusagecache_writeinput_tokens)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [openai], [openai-agents] |
| gen_ai.provider.name | [anthropic], [openai], [openai-agents] |
| gen_ai.token.modality | [anthropic], [openai], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [openai-agents] |
| gen_ai.request.model | [anthropic], [openai], [openai-agents] |
| server.port | [anthropic], [openai], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [anthropic], [openai], [openai-agents] |
| gen_ai.response.service_tier | [openai], [openai-agents] |
| server.address | [anthropic], [openai], [openai-agents] |

[anthropic]: ../scenarios/anthropic/scenario.py
[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
