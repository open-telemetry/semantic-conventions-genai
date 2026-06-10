# Create Agent Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#create-agent-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [autogen], [azure-ai-foundry], [openai-assistants] |
| gen_ai.provider.name | [autogen], [azure-ai-foundry], [openai-assistants] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | [autogen], [azure-ai-foundry], [openai-assistants] |
| gen_ai.agent.id | [azure-ai-foundry], [openai-assistants] |
| gen_ai.agent.name | [autogen], [azure-ai-foundry], [openai-assistants] |
| gen_ai.agent.version | [azure-ai-foundry] |
| gen_ai.request.model | [autogen], [azure-ai-foundry], [openai-assistants] |
| server.port | [autogen], [azure-ai-foundry], [openai-assistants] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [autogen], [azure-ai-foundry], [openai-assistants] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.system_instructions | [autogen], [azure-ai-foundry], [openai-assistants] |

[autogen]: ../scenarios/autogen/scenario.py
[azure-ai-foundry]: ../scenarios/azure-ai-foundry/scenario.py
[openai-assistants]: ../scenarios/openai-assistants/scenario.py
