# Guardrail Result Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aiguardrailresult)**

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.policy.id | [aws-bedrock] |
| gen_ai.guardrail.policy.version | [aws-bedrock] |
| gen_ai.guardrail.result.type | [aws-bedrock], [azure-ai-contentsafety], [openai-agents] |
| gen_ai.guardrail.result.value | [aws-bedrock], [azure-ai-contentsafety], [openai-agents] |
| gen_ai.guardrail.risk.category | [aws-bedrock], [azure-ai-contentsafety] |
| gen_ai.guardrail.risk.score | [azure-ai-contentsafety] |
| gen_ai.guardrail.source | [aws-bedrock], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.component.name | [aws-bedrock], [azure-ai-contentsafety], [openai-agents] |
| gen_ai.guardrail.policy.rule.id | [azure-ai-contentsafety] |
| gen_ai.guardrail.result.reason | [aws-bedrock], [openai-agents] |
| gen_ai.provider.name | [aws-bedrock], [azure-ai-contentsafety] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.content.input.value | [aws-bedrock], [azure-ai-contentsafety], [openai-agents] |
| gen_ai.guardrail.content.output.value | [aws-bedrock] |

[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-contentsafety]: ../scenarios/azure-ai-contentsafety/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
