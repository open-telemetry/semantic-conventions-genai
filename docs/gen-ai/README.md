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

Instrumentations MAY propagate context containing attributes listed below to nested
instrumentations within the same process. This allows queries to select related
spans without traversing the hierarchy.

Language-specific helper packages (such as [`opentelemetry-util-genai`](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/util/opentelemetry-util-genai))
MAY support propagating these attributes within the process.

When an attribute is available both from the instrumented library and from outer
context, instrumentation SHOULD prefer the library's value.

Instrumentations and helpers SHOULD NOT propagate attributes not listed here.
Instrumentations SHOULD NOT use these attributes on signals that don't reference them
explicitly.

* [`gen_ai.conversation.id`](/docs/registry/attributes/gen-ai.md#gen-ai-conversation-id)
* [`gen_ai.agent.name`](/docs/registry/attributes/gen-ai.md#gen-ai-agent-name)

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
