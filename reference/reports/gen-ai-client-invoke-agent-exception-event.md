# Client Invoke Agent Exception Event

> **[Semantic Convention](../../docs/gen-ai/client-invoke-agent.md#event-gen_aiclientinvoke_agentexception)**

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| exception.message | [aws-bedrock-agent], [azure-ai-foundry] |
| exception.type | [aws-bedrock-agent], [azure-ai-foundry] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| exception.stacktrace | [aws-bedrock-agent], [azure-ai-foundry] |

[aws-bedrock-agent]: ../scenarios/aws-bedrock-agent/scenario.py
[azure-ai-foundry]: ../scenarios/azure-ai-foundry/scenario.py
