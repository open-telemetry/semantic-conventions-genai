# Invoke Agent Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [agent-framework], [autogen] |
| gen_ai.agent.name | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.data_source.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.request.choice.count | [agent-framework], [crewai], [google-adk] |
| gen_ai.request.seed | [agent-framework], [autogen], [crewai], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.max_tokens | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.model | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.request.presence_penalty | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.stop_sequences | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.temperature | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.request.top_p | [agent-framework], [autogen], [crewai], [google-adk], [pydantic-ai] |
| gen_ai.response.finish_reasons | [autogen], [crewai], [google-adk], [openai-agents], [pydantic-ai] |
| gen_ai.usage.input_tokens | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.usage.output_tokens | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.output.messages | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.skills | [google-adk] |
| gen_ai.system_instructions | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |
| gen_ai.tool.definitions | [agent-framework], [autogen], [crewai], [google-adk], [langchain], [openai-agents], [pydantic-ai] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[autogen]: ../scenarios/autogen/scenario.py
[crewai]: ../scenarios/crewai/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
