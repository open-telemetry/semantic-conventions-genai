# Apply Guardrail Client Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-guardrails.md#apply-guardrail-client-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock], [azure-ai-contentsafety] |
| gen_ai.provider.name | [aws-bedrock], [azure-ai-contentsafety] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.policy.id | [aws-bedrock] |
| gen_ai.guardrail.policy.version | [aws-bedrock] |
| gen_ai.guardrail.result.type | [aws-bedrock] |
| gen_ai.guardrail.result.value | [aws-bedrock] |
| gen_ai.guardrail.source | [aws-bedrock] |
| server.port | [aws-bedrock], [azure-ai-contentsafety] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.component.name | [aws-bedrock], [azure-ai-contentsafety] |
| gen_ai.guardrail.result.reason | [aws-bedrock] |
| server.address | [aws-bedrock], [azure-ai-contentsafety] |

[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-contentsafety]: ../scenarios/azure-ai-contentsafety/scenario.py
