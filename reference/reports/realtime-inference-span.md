# Realtime Inference Span

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [google-genai], [openai] |
| gen_ai.provider.name | [google-genai], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.output.type | [google-genai], [openai] |
| gen_ai.realtime_session.id | [openai] |
| gen_ai.request.model | [google-genai], [openai] |
| server.port | [google-genai], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.max_tokens | (none) |
| gen_ai.request.reasoning.level | (none) |
| gen_ai.response.finish_reasons | [google-genai], [openai] |
| gen_ai.response.id | [openai] |
| gen_ai.response.model | [openai] |
| gen_ai.usage.audio.cache_read.input_tokens | (none) |
| gen_ai.usage.audio.input_tokens | [google-genai], [openai] |
| gen_ai.usage.audio.output_tokens | [google-genai], [openai] |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.cache_write.input_tokens | (none) |
| gen_ai.usage.image.cache_read.input_tokens | (none) |
| gen_ai.usage.image.input_tokens | (none) |
| gen_ai.usage.image.output_tokens | (none) |
| gen_ai.usage.input_tokens | [google-genai], [openai] |
| gen_ai.usage.output_tokens | [google-genai], [openai] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| gen_ai.usage.text.cache_read.input_tokens | (none) |
| gen_ai.usage.text.input_tokens | (none) |
| gen_ai.usage.text.output_tokens | (none) |
| server.address | [google-genai], [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [google-genai], [openai] |
| gen_ai.output.messages | [google-genai], [openai] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[google-genai]: ../scenarios/google-genai/scenario.py
[openai]: ../scenarios/openai/scenario.py
