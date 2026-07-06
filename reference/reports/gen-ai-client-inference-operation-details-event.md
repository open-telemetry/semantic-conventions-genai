# Inference Operation Details Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aiclientinferenceoperationdetails)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.provider.name | (none) |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.prompt.name | [aws-bedrock], [openai] |
| gen_ai.prompt.version | [aws-bedrock], [openai] |
| gen_ai.request.choice.count | [llamaindex] |
| gen_ai.request.model | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.request.seed | [pydantic-ai] |
| gen_ai.request.stream | (none) |
| gen_ai.request.top_k | (none) |
| server.port | [anthropic], [autogen], [azure-ai-inference], [openai], [pydantic-ai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.compacted | [anthropic], [openai] |
| gen_ai.request.frequency_penalty | [pydantic-ai] |
| gen_ai.request.max_tokens | [pydantic-ai] |
| gen_ai.request.presence_penalty | [pydantic-ai] |
| gen_ai.request.reasoning.level | (none) |
| gen_ai.request.stop_sequences | [pydantic-ai] |
| gen_ai.request.temperature | [pydantic-ai] |
| gen_ai.request.top_p | [pydantic-ai] |
| gen_ai.response.finish_reasons | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.response.id | [anthropic], [azure-ai-inference], [cohere], [dspy], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai] |
| gen_ai.response.model | [anthropic], [azure-ai-inference], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai] |
| gen_ai.response.time_to_first_chunk | (none) |
| gen_ai.usage.cache_creation.input_tokens | [anthropic] |
| gen_ai.usage.cache_read.input_tokens | [anthropic] |
| gen_ai.usage.input_tokens | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.usage.output_tokens | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| server.address | [anthropic], [autogen], [azure-ai-inference], [openai], [pydantic-ai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.output.messages | [anthropic], [autogen], [aws-bedrock], [azure-ai-inference], [cohere], [dspy], [google-genai], [groq], [instructor], [litellm], [llamaindex], [mistralai], [openai], [pydantic-ai], [vertexai] |
| gen_ai.prompt.variable | (none) |
| gen_ai.system_instructions | [autogen], [pydantic-ai] |
| gen_ai.tool.definitions | (none) |

[anthropic]: ../scenarios/anthropic/scenario.py
[autogen]: ../scenarios/autogen/scenario.py
[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[dspy]: ../scenarios/dspy/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[instructor]: ../scenarios/instructor/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[llamaindex]: ../scenarios/llamaindex/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
[pydantic-ai]: ../scenarios/pydantic-ai/scenario.py
[vertexai]: ../scenarios/vertexai/scenario.py
