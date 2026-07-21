# Speech-to-Text Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#speech-to-text)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai-cascade] |
| gen_ai.provider.name | [openai-cascade] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [openai-cascade] |
| server.port | [openai-cascade] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [openai-cascade] |
| gen_ai.speech.input.language | [openai-cascade] |
| gen_ai.usage.cache_creation.input_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.input_audio_tokens | (none) |
| gen_ai.usage.input_tokens | (none) |
| gen_ai.usage.output_audio_tokens | (none) |
| gen_ai.usage.output_tokens | (none) |
| server.address | [openai-cascade] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [openai-cascade] |
| gen_ai.output.messages | [openai-cascade] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[openai-cascade]: ../scenarios/openai-cascade/scenario.py
