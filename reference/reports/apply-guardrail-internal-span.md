# Apply Guardrail Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-security.md#apply-guardrail-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai] |
| gen_ai.security.target.type | [openai] |
| gen_ai.security.verdict.type | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.id | (none) |
| gen_ai.conversation.id | [openai] |
| gen_ai.security.action.type | [openai] |
| gen_ai.security.content.input.hash | [openai] |
| gen_ai.security.content.modified | [openai] |
| gen_ai.security.external_event_id | [openai] |
| gen_ai.security.guardrail.id | [openai] |
| gen_ai.security.policy.id | [openai] |
| gen_ai.security.target.id | [openai] |
| gen_ai.security.verdict.reason | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.finding.evidence | [openai] |
| gen_ai.security.guardrail.name | [openai] |
| gen_ai.security.guardrail.provider.name | [openai] |
| gen_ai.security.guardrail.version | [openai] |
| gen_ai.security.policy.name | [openai] |
| gen_ai.security.policy.rule.id | [openai] |
| gen_ai.security.policy.version | [openai] |
| gen_ai.security.risk.category | [openai] |
| gen_ai.security.risk.score | [openai] |
| gen_ai.security.verdict.code | [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.content.input.value | (none) |
| gen_ai.security.content.output.value | (none) |

[openai]: ../scenarios/openai/scenario.py
