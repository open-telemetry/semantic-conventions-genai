# Generate Live Content Span

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [gemini-live], [openai-realtime] |
| gen_ai.provider.name | [gemini-live], [openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [openai-realtime] |
| gen_ai.output.type | [gemini-live], [openai-realtime] |
| gen_ai.request.model | [gemini-live], [openai-realtime] |
| server.port | [gemini-live], [openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.max_tokens | (none) |
| gen_ai.request.reasoning.level | (none) |
| gen_ai.response.finish_reasons | [gemini-live], [openai-realtime] |
| gen_ai.response.id | [openai-realtime] |
| gen_ai.response.model | [openai-realtime] |
| gen_ai.response.time_to_first_chunk | [gemini-live], [openai-realtime] |
| gen_ai.usage.audio.input_tokens | [gemini-live], [openai-realtime] |
| gen_ai.usage.audio.output_tokens | [gemini-live], [openai-realtime] |
| gen_ai.usage.cache_creation.input_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.input_tokens | [gemini-live], [openai-realtime] |
| gen_ai.usage.output_tokens | [gemini-live], [openai-realtime] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| server.address | [gemini-live], [openai-realtime] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [gemini-live], [openai-realtime] |
| gen_ai.output.messages | [gemini-live], [openai-realtime] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[gemini-live]: ../scenarios/gemini-live/scenario.py
[openai-realtime]: ../scenarios/openai-realtime/scenario.py
