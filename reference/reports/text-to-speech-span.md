# Text-to-Speech Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#text-to-speech)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai-cascade] |
| gen_ai.provider.name | [openai-cascade] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.output.type | [openai-cascade] |
| gen_ai.request.model | [openai-cascade] |
| server.port | [openai-cascade] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [openai-cascade] |
| gen_ai.speech.voice | [openai-cascade] |
| server.address | [openai-cascade] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [openai-cascade] |
| gen_ai.output.messages | [openai-cascade] |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[openai-cascade]: ../scenarios/openai-cascade/scenario.py
