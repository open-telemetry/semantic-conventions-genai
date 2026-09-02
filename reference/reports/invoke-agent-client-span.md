# Invoke Agent Client Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-client-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [openai-assistants] |
| gen_ai.provider.name | [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [openai-assistants] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [openai-assistants] |
| gen_ai.agent.id | [aws-bedrock-agent], [openai-assistants] |
| gen_ai.agent.name | [azure-ai-foundry], [google-genai], [openai-assistants] |
| gen_ai.agent.version | [aws-bedrock-agent] |
| gen_ai.conversation.id | [aws-bedrock-agent], [openai-assistants] |
| gen_ai.data_source.id | (none) |
| gen_ai.output.type | [azure-ai-foundry] |
| gen_ai.request.choice.count | (none) |
| gen_ai.request.seed | (none) |
| server.port | [aws-bedrock-agent], [azure-ai-foundry], [openai-assistants] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | (none) |
| gen_ai.request.max_tokens | [azure-ai-foundry], [openai-assistants] |
| gen_ai.request.model | [azure-ai-foundry], [google-genai], [openai-assistants] |
| gen_ai.request.presence_penalty | (none) |
| gen_ai.request.previous_response.id | [google-genai] |
| gen_ai.request.stop_sequences | (none) |
| gen_ai.request.temperature | [azure-ai-foundry], [openai-assistants] |
| gen_ai.request.top_p | [azure-ai-foundry], [openai-assistants] |
| gen_ai.response.finish_reasons | (none) |
| gen_ai.usage.audio.cache_read.input_tokens | (none) |
| gen_ai.usage.audio.input_tokens | (none) |
| gen_ai.usage.audio.output_tokens | (none) |
| gen_ai.usage.cache_read.input_tokens | (none) |
| gen_ai.usage.cache_write.input_tokens | (none) |
| gen_ai.usage.image.cache_read.input_tokens | (none) |
| gen_ai.usage.image.input_tokens | (none) |
| gen_ai.usage.image.output_tokens | (none) |
| gen_ai.usage.input_tokens | [azure-ai-foundry], [google-genai], [openai-assistants] |
| gen_ai.usage.output_tokens | [azure-ai-foundry], [google-genai], [openai-assistants] |
| gen_ai.usage.text.cache_read.input_tokens | (none) |
| gen_ai.usage.text.input_tokens | (none) |
| gen_ai.usage.text.output_tokens | (none) |
| server.address | [aws-bedrock-agent], [azure-ai-foundry], [openai-assistants] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [aws-bedrock-agent], [azure-ai-foundry], [openai-assistants] |
| gen_ai.output.messages | [aws-bedrock-agent], [azure-ai-foundry], [openai-assistants] |
| gen_ai.system_instructions | [azure-ai-foundry], [openai-assistants] |
| gen_ai.tool.definitions | [azure-ai-foundry], [openai-assistants] |

[aws-bedrock-agent]: ../scenarios/aws-bedrock-agent/scenario.py
[azure-ai-foundry]: ../scenarios/azure-ai-foundry/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[openai-assistants]: ../scenarios/openai-assistants/scenario.py
