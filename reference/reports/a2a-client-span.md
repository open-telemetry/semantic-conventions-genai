# A2A Client Span

> **[Semantic Convention](../../docs/gen-ai/a2a.md#client)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| a2a.method.name | [a2a-python] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| a2a.message.id | [a2a-python] |
| a2a.task.id | [a2a-python] |
| a2a.task.state | [a2a-python] |
| a2a.tenant | [a2a-python] |
| gen_ai.agent.description | [a2a-python] |
| gen_ai.agent.name | [a2a-python] |
| gen_ai.agent.version | [a2a-python] |
| gen_ai.conversation.id | [a2a-python] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| a2a.message.reference_task_ids | [a2a-python] |
| a2a.protocol.version | [a2a-python] |
| server.address | [a2a-python] |
| server.port | [a2a-python] |

[a2a-python]: ../scenarios/a2a-python/scenario.py
