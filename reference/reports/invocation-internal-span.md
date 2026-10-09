# Invocation Internal Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-agent-spans.md#invocation-internal-span)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | (none) |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.agent.description | (none) |
| gen_ai.agent.name | (none) |
| gen_ai.conversation.id | (none) |
| gen_ai.data_source.id | (none) |
| gen_ai.output.type | (none) |
| gen_ai.request.choice.count | (none) |
| gen_ai.request.seed | (none) |
| gen_ai.workflow.name | (none) |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.frequency_penalty | (none) |
| gen_ai.request.max_tokens | (none) |
| gen_ai.request.model | (none) |
| gen_ai.request.presence_penalty | (none) |
| gen_ai.request.stop_sequences | (none) |
| gen_ai.request.temperature | (none) |
| gen_ai.request.top_p | (none) |
| gen_ai.response.finish_reasons | (none) |
| gen_ai.usage.input_tokens | (none) |
| gen_ai.usage.output_tokens | (none) |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.input.messages | (none) |
| gen_ai.output.messages | (none) |
| gen_ai.system_instructions | (none) |
| gen_ai.tool.definitions | (none) |
