# Memory Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#memory)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock-agentcore], [google-adk], [mem0] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.record.id | [aws-bedrock-agentcore] |
| gen_ai.memory.store.id | [aws-bedrock-agentcore], [google-adk] |
| gen_ai.provider.name | [aws-bedrock-agentcore] |
| server.port | [aws-bedrock-agentcore] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.record.count | [aws-bedrock-agentcore], [google-adk], [mem0] |
| server.address | [aws-bedrock-agentcore] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.query.text | [aws-bedrock-agentcore], [google-adk], [mem0] |
| gen_ai.memory.records | [aws-bedrock-agentcore], [google-adk], [mem0] |

[aws-bedrock-agentcore]: ../scenarios/aws-bedrock-agentcore/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[mem0]: ../scenarios/mem0/scenario.py
