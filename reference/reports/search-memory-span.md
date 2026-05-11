# Search Memory Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#search-memory)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-adk] |
| gen_ai.provider.name | [google-adk] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.store.id | [google-adk] |
| server.port | (none) |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | (none) |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.memory.query.text | [google-adk] |
| gen_ai.memory.records | [google-adk] |

[google-adk]: ../scenarios/google-adk/scenario.py
