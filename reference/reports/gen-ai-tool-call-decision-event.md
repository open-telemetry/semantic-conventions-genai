# Tool Call Decision Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aitoolcalldecision)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.tool.call.decision.outcome | [agent-framework], [claude-agent-sdk], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.tool.call.id | [agent-framework], [claude-agent-sdk], [openai-agents] |
| gen_ai.tool.name | [agent-framework], [claude-agent-sdk], [openai-agents] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[claude-agent-sdk]: ../scenarios/claude-agent-sdk/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
