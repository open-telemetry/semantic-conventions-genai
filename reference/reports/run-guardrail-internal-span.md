# Run Guardrail Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-security.md#run-guardrail-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.target.type | [openai], [openai-guardrails] |
| gen_ai.guardrail.verdict.type | [openai], [openai-guardrails] |
| gen_ai.operation.name | [openai], [openai-guardrails] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [openai] |
| gen_ai.guardrail.action.type | [openai], [openai-guardrails] |
| gen_ai.guardrail.security.content.input.hash | [openai] |
| gen_ai.guardrail.security.content.modified | [openai] |
| gen_ai.guardrail.security.external_finding_id | [openai] |
| gen_ai.guardrail.security.policy.id | [openai] |
| gen_ai.guardrail.target.id | [openai] |
| gen_ai.guardrail.target.subtype | [openai], [openai-guardrails] |
| gen_ai.guardrail.verdict.reason | [openai], [openai-guardrails] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.component.name | [openai], [openai-guardrails] |
| gen_ai.guardrail.security.policy.rule.id | [openai] |
| gen_ai.guardrail.security.risk.category | [openai] |
| gen_ai.guardrail.security.risk.score | [openai] |
| gen_ai.guardrail.verdict.code | [openai] |
| gen_ai.provider.name | [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.security.content.input.value | (none) |
| gen_ai.guardrail.security.content.output.value | (none) |

[openai]: ../scenarios/openai/scenario.py
[openai-guardrails]: ../scenarios/openai-guardrails/scenario.py
