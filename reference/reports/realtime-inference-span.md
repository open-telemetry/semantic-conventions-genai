# Realtime Inference Span

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.provider.name | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | (none) |
| gen_ai.output.type | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.realtime_session.id | [openai][openai@openai-realtime] |
| gen_ai.request.model | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| server.port | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.max_tokens | (none) |
| gen_ai.request.reasoning.level | (none) |
| gen_ai.response.finish_reasons | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.response.id | [openai][openai@openai-realtime] |
| gen_ai.response.model | [openai][openai@openai-realtime] |
| gen_ai.usage.audio.cache_read.input_tokens | (none) |
| gen_ai.usage.audio.input_tokens | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.usage.audio.output_tokens | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.cache_write.input_tokens | (none) |
| gen_ai.usage.image.cache_read.input_tokens | (none) |
| gen_ai.usage.image.input_tokens | (none) |
| gen_ai.usage.image.output_tokens | (none) |
| gen_ai.usage.input_tokens | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.usage.output_tokens | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| gen_ai.usage.text.cache_read.input_tokens | (none) |
| gen_ai.usage.text.input_tokens | (none) |
| gen_ai.usage.text.output_tokens | (none) |
| server.address | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.output.messages | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[google-genai@gemini-live]: ../scenarios/gemini-live/scenario.py
[openai@openai-realtime]: ../scenarios/openai-realtime/scenario.py
