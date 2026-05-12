# Upsert Memory Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#upsert-memory)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-adk] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.store.id | [google-adk] |
| gen_ai.provider.name | (none) |
| server.port | (none) |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.record.count | [google-adk] |
| server.address | (none) |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.records | [google-adk] |

[google-adk]: ../scenarios/google-adk/scenario.py
