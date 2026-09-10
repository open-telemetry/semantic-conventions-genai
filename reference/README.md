# Semantic Conventions GenAI Reference Implementations

Validates [OpenTelemetry Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
against real LLM client libraries in Python, showing which libraries
support which attributes.

Each library under [scenarios/](scenarios/) contains a small reference implementation
(`scenario.py`) that exercises the SDK against a deterministic local mock server
and emits OpenTelemetry spans, metrics, and logs, plus a `conformance.yaml`
saying how to run it. The
[conformance runner](https://github.com/open-telemetry/semantic-conventions-conformance)
validates the captured telemetry against the semantic conventions in
[../model/](../model/) using [OTel Weaver](https://github.com/open-telemetry/weaver)
and writes the per-library results to `scenarios/<library>/data.json`, which
feed the status reports below.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run scenarios and add new libraries.

## Reports

Generated from committed `scenarios/*/data.json` files. Do not edit this section by hand.
Run `uv run update-reports` to regenerate.

<!-- status:begin -->
### Spans

| Span | Libraries |
| --- | --- |
| [Create Agent](reports/create-agent-span.md) | anthropic, aws-bedrock-agent, azure-ai-foundry, google-genai, mistralai, openai-assistants |
| [Invoke Agent Client](reports/invoke-agent-client-span.md) | aws-bedrock-agent, azure-ai-foundry, google-genai, openai-assistants |
| [Invoke Agent Internal](reports/invoke-agent-internal-span.md) | agent-framework, autogen, crewai, google-adk, langchain, openai-agents, pydantic-ai |
| [Invoke Workflow](reports/invoke-workflow-span.md) | crewai, google-adk, langchain, openai-agents |
| [Plan](reports/plan-span.md) | crewai, langchain |
| [Inference](reports/inference-span.md) | agent-framework, anthropic, aws-bedrock, azure-ai-inference, azure-openai, claude-agent-sdk, cohere, google-genai, groq, litellm, mistralai, openai, vertexai |
| [Embeddings](reports/embeddings-span.md) | aws-bedrock, azure-ai-inference, azure-openai, cohere, google-genai, litellm, mistralai, openai |
| [Retrieval](reports/retrieval-span.md) | haystack, langchain, llamaindex |
| [Fetch Response](reports/fetch-response-span.md) | openai |
| [Memory](reports/memory-span.md) | aws-bedrock-agentcore, google-adk |
| [Execute Tool](reports/execute-tool-span.md) | agent-framework, autogen, crewai, google-adk, google-genai, langchain, llamaindex, openai-agents, openai-assistants, pydantic-ai, vertexai |

### Events

| Event | Libraries |
| --- | --- |
| [Inference Operation Details](reports/gen-ai-client-inference-operation-details-event.md) | anthropic, aws-bedrock, azure-ai-inference, cohere, google-genai, groq, litellm, mistralai, openai, vertexai |
| [Evaluation Result](reports/gen-ai-evaluation-result-event.md) | azure-ai-evaluation, deepeval, dspy |

### Metrics

| Metric | Libraries |
| --- | --- |
| [Client Token Usage](reports/gen-ai-client-token-usage-metric.md) | agent-framework, anthropic, groq |
| [Client Operation Duration](reports/gen-ai-client-operation-duration-metric.md) | agent-framework, anthropic, groq |
| [Invoke Agent Inference Calls](reports/gen-ai-invoke-agent-inference-calls-metric.md) | google-adk |
| [Invoke Agent Tool Calls](reports/gen-ai-invoke-agent-tool-calls-metric.md) | google-adk |
| [Invoke Agent Skill Loads](reports/gen-ai-invoke-agent-skill-loads-metric.md) | agent-framework, google-adk |
| [Invoke Workflow Skill Loads](reports/gen-ai-invoke-workflow-skill-loads-metric.md) | google-adk |
| [Skill Loads](reports/gen-ai-skill-loads-metric.md) | agent-framework, google-adk |
| [Skill Script Executions](reports/gen-ai-skill-script-executions-metric.md) | agent-framework, google-adk |
<!-- status:end -->
