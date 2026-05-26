# Context Selection Evaluated Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aicontextselectionevaluated)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.context.selection.candidate.count | [anthropic] |
| gen_ai.context.selection.selected.count | [anthropic] |
| gen_ai.context.selection.suppressed.count | [anthropic] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.id | (none) |
| gen_ai.context.selection.delivered_hash.count | [anthropic] |
| gen_ai.context.selection.policy | [anthropic] |
| gen_ai.conversation.id | (none) |

[anthropic]: ../scenarios/anthropic/scenario.py
