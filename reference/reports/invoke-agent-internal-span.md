# Invoke Agent Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.provider.name | [autogen], [crewai], [google-adk], [pydantic-ai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [autogen] |
| gen_ai.agent.name | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.agent.version | (none) |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.data_source.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.request.choice.count | [crewai], [google-adk] |
| gen_ai.request.model | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.seed | [autogen], [crewai], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.max_tokens | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.presence_penalty | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.stop_sequences | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.temperature | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.top_p | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.response.finish_reasons | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.usage.cache_creation.input_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.input_tokens | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.usage.output_tokens | [autogen], [crewai], [google-adk], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.output.messages | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.system_instructions | [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.tool.definitions | [autogen], [crewai], [google-adk], [pydantic-ai] |

[autogen]: ../scenarios/autogen/scenario.py
[crewai]: ../scenarios/crewai/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
