# Invoke Agent Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.provider.name | [autogen], [google-adk], [pydantic-ai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [autogen] |
| gen_ai.agent.id | (none) |
| gen_ai.agent.name | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.agent.version | (none) |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.data_source.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.request.choice.count | [google-adk] |
| gen_ai.request.model | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.seed | [autogen], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.max_tokens | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.presence_penalty | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.stop_sequences | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.temperature | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.request.top_p | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.response.finish_reasons | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.usage.cache_creation.input_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.input_tokens | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.usage.output_tokens | [autogen], [google-adk], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.output.messages | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.system_instructions | [autogen], [google-adk], [pydantic-ai] |
| gen_ai.tool.definitions | [autogen], [google-adk], [pydantic-ai] |

[autogen]: ../scenarios/autogen/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
