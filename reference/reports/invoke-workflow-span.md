# Invoke Workflow Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invoke-workflow-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [crewai], [google-adk], [langchain], [openai-agents] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [google-adk] |
| gen_ai.workflow.name | [crewai], [google-adk], [langchain], [openai-agents] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.external_ref | (none) |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | [crewai], [google-adk], [langchain], [openai-agents] |
| gen_ai.output.messages | [crewai], [google-adk], [langchain], [openai-agents] |

[crewai]: ../scenarios/crewai/scenario.py
[google-adk]: ../scenarios/google-adk/scenario.py
[langchain]: ../scenarios/langchain/scenario.py
[openai-agents]: ../scenarios/openai-agents/scenario.py
