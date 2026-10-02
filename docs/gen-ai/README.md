<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Generative AI
--->

# Semantic conventions for generative AI systems

**Status**: [Development][DocumentStatus]

Semantic conventions for Generative AI operations are defined for the following signals:

* [Events](gen-ai-events.md): Semantic Conventions for Generative AI inputs and outputs - *events*.
* [Exceptions](gen-ai-exceptions.md): Semantic Conventions for Generative AI *exceptions*.
* [Metrics](gen-ai-metrics.md): Semantic Conventions for Generative AI operations - *metrics*.
* [Inference Token Metrics](gen-ai-token-metrics.md): Semantic Conventions for Generative AI inference token metrics - *metrics*.
* [Model spans](gen-ai-spans.md): Semantic Conventions for Generative AI model operations - *spans*.
* [Agent spans](gen-ai-agent-spans.md): Semantic Conventions for Generative AI agent operations - *spans*.

Technology specific semantic conventions are defined for the following GenAI system:

* [Anthropic](./anthropic.md): Semantic Conventions for Anthropic.
* [Azure AI Inference](./azure-ai-inference.md): Semantic Conventions for Azure AI Inference.
* [AWS Bedrock](./aws-bedrock.md): Semantic Conventions for AWS Bedrock.
* [OpenAI](./openai.md): Semantic Conventions for OpenAI.

See also:

* [Model Context Protocol](./mcp.md): Semantic Conventions for [MCP](https://modelcontextprotocol.io)

## Attributes shared across operations

Conversation and agent attributes appear on several GenAI operations, allowing
queries to select related work without traversing the span hierarchy. The table
below summarizes their existing use. Follow each signal's attribute requirements
and availability conditions when recording them.

| Attribute | Use across spans | Use on metrics |
| --- | --- | --- |
| [`gen_ai.conversation.id`](/docs/registry/attributes/gen-ai.md) | Correlates [remote](gen-ai-agent-spans.md#invoke-agent-client-span) and [local](gen-ai-agent-spans.md#invoke-agent-internal-span) agent invocations, [workflow invocations](gen-ai-agent-spans.md#invoke-workflow-span), [inference](gen-ai-spans.md#inference), and [tool executions](gen-ai-spans.md#execute-tool-span) belonging to the same conversation. | Not defined on GenAI metrics. |
| [`gen_ai.agent.name`](/docs/registry/attributes/gen-ai.md) | Identifies the agent being [created](gen-ai-agent-spans.md#create-agent-span) or invoked, either [remotely](gen-ai-agent-spans.md#invoke-agent-client-span) or [locally](gen-ai-agent-spans.md#invoke-agent-internal-span), and the agent [planning](gen-ai-agent-spans.md#plan-span) or [executing a tool](gen-ai-spans.md#execute-tool-span). It is not currently defined on inference spans. | Included in [agent metrics](gen-ai-metrics.md#generative-ai-agent-metrics) and [tool metrics](gen-ai-metrics.md#generative-ai-tool-metrics). |

Use the conversation identifier available to the instrumented library or supplied
by the application. Leave it unset when unavailable, as described in the
[attribute definition](/docs/registry/attributes/gen-ai.md#gen-ai-conversation-id).
An agent name describes the agent involved in that operation; a nested agent
invocation can name a different agent from its parent.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
