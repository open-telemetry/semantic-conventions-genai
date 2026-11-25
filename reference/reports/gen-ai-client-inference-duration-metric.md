# Client Inference Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferenceduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [anthropic], [groq], [openai-agents] |
| gen_ai.provider.name | [agent-framework], [anthropic], [groq], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [openai-agents] |
| gen_ai.request.model | [agent-framework], [anthropic], [groq], [openai-agents] |
| server.port | [anthropic], [groq], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [agent-framework], [anthropic], [groq], [openai-agents] |
| gen_ai.response.service_tier | [groq], [openai-agents] |
| server.address | [agent-framework], [anthropic], [groq], [openai-agents] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
[groq]: ../scenarios/groq/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
