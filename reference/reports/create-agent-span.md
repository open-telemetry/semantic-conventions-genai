# Create Agent Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#create-agent-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |
| gen_ai.provider.name | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |
| gen_ai.agent.id | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |
| gen_ai.agent.name | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |
| gen_ai.agent.version | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [mistralai] |
| gen_ai.request.model | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |
| server.port | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [mistralai], [openai-assistants] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [mistralai], [openai-assistants] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.system_instructions | [anthropic], [aws-bedrock-agent], [azure-ai-foundry], [google-genai], [mistralai], [openai-assistants] |

[anthropic]: ../scenarios/anthropic/scenario.py
[aws-bedrock-agent]: ../scenarios/aws-bedrock-agent/scenario.py
[azure-ai-foundry]: ../scenarios/azure-ai-foundry/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai-assistants]: ../scenarios/openai-assistants/scenario.py
