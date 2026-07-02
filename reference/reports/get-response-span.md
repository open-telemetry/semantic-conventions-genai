# Get Response Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#get-response)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai] |
| gen_ai.provider.name | [openai] |
| gen_ai.response.id | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| server.port | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.finish_reasons | [openai] |
| gen_ai.response.model | [openai] |
| server.address | [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | (none) |
| gen_ai.output.messages | (none) |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |
| gen_ai.usage.input_tokens | [openai] |
| gen_ai.usage.output_tokens | [openai] |

[openai]: ../scenarios/openai/scenario.py
