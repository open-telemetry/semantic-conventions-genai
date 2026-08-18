# Inference Operation Details Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aiclientinferenceoperationdetails)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.provider.name | [anthropic], [google-genai], [openai], [vertexai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.prompt.name | [aws-bedrock], [openai] |
| gen_ai.prompt.version | [aws-bedrock], [openai] |
| gen_ai.request.choice.count | (none) |
| gen_ai.request.model | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.request.seed | (none) |
| gen_ai.request.stream | (none) |
| gen_ai.request.top_k | (none) |
| server.port | [anthropic], [azure-ai-inference], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.compacted | [anthropic], [openai] |
| gen_ai.request.frequency_penalty | (none) |
| gen_ai.request.max_tokens | [anthropic] |
| gen_ai.request.presence_penalty | (none) |
| gen_ai.request.previous_response.id | [google-genai], [openai] |
| gen_ai.request.reasoning.level | [anthropic] |
| gen_ai.request.stop_sequences | (none) |
| gen_ai.request.temperature | (none) |
| gen_ai.request.top_p | (none) |
| gen_ai.response.finish_reasons | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.response.id | [anthropic], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai] |
| gen_ai.response.model | [anthropic], [azure-ai-inference], [google-genai], [groq], [litellm], [mistralai], [openai] |
| gen_ai.response.time_to_first_chunk | (none) |
| gen_ai.usage.audio.cache_read.input_tokens | [google-genai], [vertexai] |
| gen_ai.usage.audio.input_tokens | [google-genai], [openai], [vertexai] |
| gen_ai.usage.audio.output_tokens | [google-genai], [openai] |
| gen_ai.usage.cache_read.input_tokens | [anthropic], [google-genai], [openai], [vertexai] |
| gen_ai.usage.cache_write.input_tokens | [anthropic], [openai] |
| gen_ai.usage.image.cache_read.input_tokens | [google-genai], [vertexai] |
| gen_ai.usage.image.input_tokens | [google-genai], [vertexai] |
| gen_ai.usage.image.output_tokens | [google-genai] |
| gen_ai.usage.input_tokens | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.usage.output_tokens | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.usage.reasoning.output_tokens | [google-genai], [openai], [vertexai] |
| gen_ai.usage.text.cache_read.input_tokens | [google-genai], [vertexai] |
| gen_ai.usage.text.input_tokens | [google-genai], [vertexai] |
| gen_ai.usage.text.output_tokens | [google-genai], [vertexai] |
| server.address | [anthropic], [azure-ai-inference], [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.output.messages | [anthropic], [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.prompt.variable | (none) |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |

[anthropic]: ../scenarios/anthropic/scenario.py
[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
[vertexai]: ../scenarios/vertexai/scenario.py
