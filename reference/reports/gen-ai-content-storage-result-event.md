# Content Storage Result Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aicontentstorageresult)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.content.storage.status | [opentelemetry-util-genai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages_ref | [opentelemetry-util-genai] |
| gen_ai.output.messages_ref | [opentelemetry-util-genai] |
| gen_ai.system_instructions_ref | [opentelemetry-util-genai] |

[opentelemetry-util-genai]: ../scenarios/opentelemetry-util-genai/scenario.py
