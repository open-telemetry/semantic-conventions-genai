# Invoke Workflow Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-workflow-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [crewai], [google-adk] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.workflow.name | [crewai], [google-adk] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [crewai], [google-adk] |
| gen_ai.output.messages | [crewai], [google-adk] |

[crewai]: ../scenarios/crewai/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
