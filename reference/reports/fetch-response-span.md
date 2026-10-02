# Fetch Response Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#fetch-response)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai] |
| gen_ai.provider.name | [openai] |
| gen_ai.response.id | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.stream_cursor | [openai] |
| server.port | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.external_ref | (none) |
| gen_ai.response.finish_reasons | [openai] |
| gen_ai.response.model | [openai] |
| gen_ai.response.status | [openai] |
| server.address | [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.output.messages | [openai] |
| gen_ai.system_instructions | [openai] |
| gen_ai.tool.definitions | (none) |

[openai]: ../scenarios/openai/scenario.py
