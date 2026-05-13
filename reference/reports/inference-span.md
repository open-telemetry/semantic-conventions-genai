# Inference Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#inference)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |
| gen_ai.provider.name | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.output.type | (none) |
| gen_ai.request.choice.count | [crewai], [google-adk], [llamaindex], [openai] |
| gen_ai.request.model | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |
| gen_ai.request.seed | [autogen], [crewai], [openai], [pydantic-ai] |
| gen_ai.request.stream | (none) |
| gen_ai.request.top_k | [google-adk] |
| server.port | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [crewai], [google-adk], [langchain], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | [autogen], [crewai], [google-adk], [openai], [pydantic-ai] |
| gen_ai.request.max_tokens | [anthropic], [autogen], [crewai], [google-adk], [openai], [pydantic-ai] |
| gen_ai.request.presence_penalty | [autogen], [crewai], [google-adk], [openai], [pydantic-ai] |
| gen_ai.request.stop_sequences | [autogen], [crewai], [google-adk], [openai], [pydantic-ai] |
| gen_ai.request.temperature | [autogen], [crewai], [google-adk], [llamaindex], [openai], [pydantic-ai] |
| gen_ai.request.top_p | [autogen], [crewai], [google-adk], [openai], [pydantic-ai] |
| gen_ai.response.finish_reasons | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.response.id | [anthropic], [autogen], [azure-ai-inference], [azure-openai], [cohere], [crewai], [dspy], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai] |
| gen_ai.response.model | [anthropic], [autogen], [azure-ai-inference], [azure-openai], [crewai], [dspy], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai] |
| gen_ai.response.time_to_first_chunk | (none) |
| gen_ai.usage.cache_creation.input_tokens | [anthropic] |
| gen_ai.usage.cache_read.input_tokens | [anthropic] |
| gen_ai.usage.input_tokens | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |
| gen_ai.usage.output_tokens | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| server.address | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [crewai], [google-adk], [langchain], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [anthropic], [autogen], [aws-bedrock], [claude-agent-sdk], [crewai], [dspy], [google-adk], [groq], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai] |
| gen_ai.output.messages | [anthropic], [autogen], [aws-bedrock], [claude-agent-sdk], [crewai], [dspy], [google-adk], [instructor], [langchain], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai] |
| gen_ai.system_instructions | [autogen], [crewai], [google-adk], [langchain], [openai], [pydantic-ai] |
| gen_ai.tool.definitions | [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [crewai], [dspy], [google-adk], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [openai-agents], [pydantic-ai], [vertexai] |

[anthropic]: ../scenarios/anthropic/scenario.py
[autogen]: ../scenarios/autogen/scenario.py
[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[claude-agent-sdk]: ../scenarios/claude-agent-sdk/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[crewai]: ../scenarios/crewai/scenario.py
[dspy]: ../scenarios/dspy/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[instructor]: ../scenarios/instructor/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
[vertexai]: ../scenarios/vertexai/scenario.py
