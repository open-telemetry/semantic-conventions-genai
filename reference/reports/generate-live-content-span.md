# Generate Live Content Span

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.provider.name | [gemini-live], [gemini-live-3], [openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [openai-realtime] |
| gen_ai.output.type | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.request.model | [gemini-live], [gemini-live-3], [openai-realtime] |
| server.port | [gemini-live], [gemini-live-3], [openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.max_tokens | (none) |
| gen_ai.request.reasoning.level | (none) |
| gen_ai.response.finish_reasons | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.response.id | [openai-realtime] |
| gen_ai.response.model | [openai-realtime] |
| gen_ai.response.time_to_first_chunk | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.usage.audio.input_tokens | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.usage.audio.output_tokens | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.usage.cache_creation.input_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.input_tokens | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.usage.output_tokens | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| server.address | [gemini-live], [gemini-live-3], [openai-realtime] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.output.messages | [gemini-live], [gemini-live-3], [openai-realtime] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[gemini-live]: ../scenarios/gemini-live/scenario.py
[gemini-live-3]: ../scenarios/gemini-live-3/scenario.py
[openai-realtime]: ../scenarios/openai-realtime/scenario.py
