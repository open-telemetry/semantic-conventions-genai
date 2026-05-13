# Semantic Conventions GenAI Reference Implementations

Validates [OpenTelemetry Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
against real LLM client libraries in Python, showing which libraries
support which attributes.

Each library under [scenarios/](scenarios/) contains a small reference implementation
(`scenario.py`) that exercises the SDK against a deterministic local mock server
and emits OpenTelemetry spans, metrics, and logs. The tooling validates the
captured telemetry against the semantic conventions in [../model/](../model/)
using [OTel Weaver](https://github.com/open-telemetry/weaver) and writes the
per-library results to `scenarios/<library>/data.json`, which feed the status
reports below.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run scenarios and add new libraries.

## Reports

Generated from committed `scenarios/*/data.json` files. Do not edit this section by hand.
Run `uv run update-reports` to regenerate.

<!-- status:begin -->
### Spans

| Span | Libraries |
| --- | --- |
| [Create Agent](reports/create-agent-span.md) | autogen, azure-ai-foundry, crewai, openai-assistants |
| [Invoke Agent Client](reports/invoke-agent-client-span.md) | aws-bedrock-agent, azure-ai-foundry, openai-agents, openai-assistants |
| [Invoke Agent Internal](reports/invoke-agent-internal-span.md) | autogen, google-adk, pydantic-ai |
| [Invoke Workflow](reports/invoke-workflow-span.md) | crewai, google-adk |
| [Plan](reports/plan-span.md) | crewai, langchain |
| [Inference](reports/inference-span.md) | anthropic, autogen, aws-bedrock, azure-ai-inference, azure-openai, claude-agent-sdk, cohere, crewai, dspy, google-adk, google-genai, groq, instructor, langchain, litellm, llamaindex, mistralai, openai, openai-agents, pydantic-ai, vertexai |
| [Embeddings](reports/embeddings-span.md) | aws-bedrock, azure-ai-inference, azure-openai, cohere, google-genai, litellm, llamaindex, mistralai, openai |
| [Retrieval](reports/retrieval-span.md) | haystack, langchain, llamaindex |
| [Execute Tool](reports/execute-tool-span.md) | autogen, crewai, google-adk, groq, instructor, litellm, llamaindex, mistralai, openai, openai-agents, openai-assistants, pydantic-ai |

### Events

| Event | Libraries |
| --- | --- |
| [Inference Operation Details](reports/gen-ai-client-inference-operation-details-event.md) | anthropic, autogen, aws-bedrock, azure-ai-inference, cohere, dspy, google-genai, groq, instructor, litellm, llamaindex, mistralai, openai, pydantic-ai, vertexai |
| [Evaluation Result](reports/gen-ai-evaluation-result-event.md) | azure-ai-evaluation, deepeval, dspy |
<!-- status:end -->
