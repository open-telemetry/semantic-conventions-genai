# Security Finding Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-security.md#finding-gen_aisecurityfinding)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.policy.id | [openai] |
| gen_ai.security.risk.finding | [openai] |
| gen_ai.security.target.type | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.external_finding_id | [openai] |
| gen_ai.security.target.id | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.action.type | [openai] |
| gen_ai.security.finding.evidence | [openai] |
| gen_ai.security.guardrail.id | [openai] |
| gen_ai.security.guardrail.name | [openai] |
| gen_ai.security.guardrail.provider.name | [openai] |
| gen_ai.security.policy.name | [openai] |
| gen_ai.security.policy.rule.id | [openai] |
| gen_ai.security.policy.version | [openai] |
| gen_ai.security.risk.score | [openai] |
| gen_ai.security.verdict.code | [openai] |
| gen_ai.security.verdict.reason | [openai] |
| gen_ai.security.verdict.type | [openai] |

[openai]: ../scenarios/openai/scenario.py
