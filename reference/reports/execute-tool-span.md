# Execute Tool Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#execute-tool-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |
| gen_ai.tool.name | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [external-ref], [google-adk], [openai-agents], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.external_ref | (none) |
| gen_ai.tool.call.id | [agent-framework], [autogen], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |
| gen_ai.tool.description | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |
| gen_ai.tool.type | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.tool.call.arguments | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |
| gen_ai.tool.call.result | [agent-framework], [autogen], [crewai], [external-ref], [google-adk], [google-genai], [langchain], [llamaindex], [openai-agents], [openai-assistants], [pydantic-ai], [vertexai] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[autogen]: ../scenarios/autogen/scenario.py
[crewai]: ../scenarios/crewai/scenario.py
[external-ref]: ../scenarios/external-ref/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
[openai-assistants]: ../scenarios/openai-assistants/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
[vertexai]: ../scenarios/vertexai/scenario.py
