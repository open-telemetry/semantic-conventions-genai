# Execute Tool Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#execute-tool-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [agent-framework], [autogen], [crewai], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |
| gen_ai.tool.name | [agent-framework], [autogen], [crewai], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.name | [google-adk], [openai-agents], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.tool.call.id | [agent-framework], [autogen], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |
| gen_ai.tool.description | [agent-framework], [autogen], [crewai], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [pydantic-ai] |
| gen_ai.tool.type | [agent-framework], [autogen], [crewai], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.tool.call.arguments | [agent-framework], [autogen], [crewai], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |
| gen_ai.tool.call.result | [agent-framework], [autogen], [crewai], [gemini-live], [gemini-live-3], [google-adk], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [openai-assistants], [openai-realtime], [pydantic-ai] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[autogen]: ../scenarios/autogen/scenario.py
[crewai]: ../scenarios/crewai/scenario.py
[gemini-live]: ../scenarios/gemini-live/scenario.py
[gemini-live-3]: ../scenarios/gemini-live-3/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[groq]: ../scenarios/groq/scenario.py
[instructor]: ../scenarios/instructor/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
[openai-assistants]: ../scenarios/openai-assistants/scenario.py
[openai-realtime]: ../scenarios/openai-realtime/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
