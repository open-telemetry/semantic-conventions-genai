# Security Finding Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aiguardrailsecurityfinding)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.security.policy.id | [openai] |
| gen_ai.guardrail.security.risk.category | [openai] |
| gen_ai.guardrail.target.type | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.security.external_finding_id | [openai] |
| gen_ai.guardrail.target.id | [openai] |
| gen_ai.guardrail.target.subtype | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.guardrail.action.type | [openai] |
| gen_ai.guardrail.component.name | [openai] |
| gen_ai.guardrail.security.policy.rule.id | [openai] |
| gen_ai.guardrail.security.risk.score | [openai] |
| gen_ai.guardrail.verdict.code | [openai] |
| gen_ai.guardrail.verdict.reason | [openai] |
| gen_ai.guardrail.verdict.type | [openai] |
| gen_ai.provider.name | [openai] |

[openai]: ../scenarios/openai/scenario.py
