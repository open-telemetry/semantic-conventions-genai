# Run Step Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#run-step-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [crewai], [google-adk], [langchain] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.step.name | [crewai], [google-adk], [langchain] |

[crewai]: ../scenarios/crewai/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
