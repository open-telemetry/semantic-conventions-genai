# Inference Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#inference)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.provider.name | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.prompt.name | [aws-bedrock], [openai] |
| gen_ai.prompt.version | [aws-bedrock], [openai] |
| gen_ai.request.choice.count | [openai] |
| gen_ai.request.model | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.request.seed | [openai] |
| gen_ai.request.stream | [openai] |
| gen_ai.request.top_k | (none) |
| server.port | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [mistralai], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.compacted | [anthropic], [openai] |
| gen_ai.request.frequency_penalty | [openai] |
| gen_ai.request.max_tokens | [anthropic], [openai] |
| gen_ai.request.presence_penalty | [openai] |
| gen_ai.request.reasoning.level | [anthropic], [openai] |
| gen_ai.request.stop_sequences | [openai] |
| gen_ai.request.temperature | [openai] |
| gen_ai.request.top_p | [openai] |
| gen_ai.response.finish_reasons | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.response.id | [anthropic], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [groq], [litellm], [mistralai], [openai] |
| gen_ai.response.model | [anthropic], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [google-genai], [groq], [litellm], [mistralai], [openai] |
| gen_ai.response.time_to_first_chunk | (none) |
| gen_ai.usage.cache_creation.input_tokens | [anthropic] |
| gen_ai.usage.cache_read.input_tokens | [anthropic] |
| gen_ai.usage.input_tokens | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.usage.output_tokens | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [claude-agent-sdk], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |
| gen_ai.usage.reasoning.output_tokens | (none) |
| server.address | [anthropic], [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [mistralai], [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [anthropic], [aws-bedrock], [claude-agent-sdk], [groq], [litellm], [mistralai], [openai] |
| gen_ai.output.messages | [anthropic], [aws-bedrock], [claude-agent-sdk], [litellm], [mistralai], [openai] |
| gen_ai.prompt.variable | (none) |
| gen_ai.system_instructions | [openai] |
| gen_ai.tool.definitions | [aws-bedrock], [azure-ai-inference], [cohere], [google-genai], [groq], [litellm], [mistralai], [openai], [vertexai] |

[agent-framework]: ../scenarios/agent-framework/scenario.py
[anthropic]: ../scenarios/anthropic/scenario.py
[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[claude-agent-sdk]: ../scenarios/claude-agent-sdk/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[groq]: ../scenarios/groq/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
[vertexai]: ../scenarios/vertexai/scenario.py
