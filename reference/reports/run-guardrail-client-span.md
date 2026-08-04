# Run Guardrail Client Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-security.md#run-guardrail-client-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [openai] |
| gen_ai.security.target.type | [openai] |
| gen_ai.security.verdict.type | [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | (none) |
| gen_ai.security.action.type | [openai] |
| gen_ai.security.content.input.hash | (none) |
| gen_ai.security.content.modified | (none) |
| gen_ai.security.external_finding_id | (none) |
| gen_ai.security.policy.id | [openai] |
| gen_ai.security.target.id | [openai] |
| gen_ai.security.target.subtype | [openai] |
| gen_ai.security.verdict.reason | (none) |
| server.port | [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [openai] |
| gen_ai.security.guardrail.name | [openai] |
| gen_ai.security.policy.name | [openai] |
| gen_ai.security.policy.rule.id | (none) |
| gen_ai.security.policy.version | [openai] |
| gen_ai.security.risk.finding | (none) |
| gen_ai.security.risk.score | (none) |
| gen_ai.security.verdict.code | (none) |
| server.address | [openai] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.security.content.input.value | (none) |
| gen_ai.security.content.output.value | (none) |

[openai]: ../scenarios/openai/scenario.py
