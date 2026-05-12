# Delete Memory Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#delete-memory)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock-agentcore] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.record.id | [aws-bedrock-agentcore] |
| gen_ai.memory.store.id | [aws-bedrock-agentcore] |
| gen_ai.provider.name | [aws-bedrock-agentcore] |
| server.port | [aws-bedrock-agentcore] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [aws-bedrock-agentcore] |

[aws-bedrock-agentcore]: ../scenarios/aws-bedrock-agentcore/scenario.py
