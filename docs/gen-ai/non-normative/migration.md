<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Migration
--->

# Generative AI semantic conventions migration guide

> [!WARNING]
> This document is a work in progress. The GenAI semantic conventions are in
> development, and breaking changes are still being made.

This guide covers changes to the GenAI semantic conventions from
[v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/README.md),
the last version published in
[open-telemetry/semantic-conventions](https://github.com/open-telemetry/semantic-conventions),
to TODO (latest).

- [Key scenarios](#key-scenarios) shows how to update common dashboard and
  alert queries.
- [Summary of changes](#summary-of-changes) lists every change.

## Key scenarios

Queries are written in PromQL; adapt them to your backend.

| Scenario | v1.41.0 | Now |
| --- | --- | --- |
| Model calls by model | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.operation.duration_count", "gen_ai.operation.name"=~"chat\|generate_content\|text_completion"}[5m]))` | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.inference.duration_count"}[5m]))` |
| Model call latency p95 by model | `histogram_quantile(0.95, sum by ("le", "gen_ai.request.model") (rate({"gen_ai.client.operation.duration_bucket", "gen_ai.operation.name"=~"chat\|generate_content\|text_completion"}[5m])))` | `histogram_quantile(0.95, sum by ("le", "gen_ai.request.model") (rate({"gen_ai.client.inference.duration_bucket"}[5m])))` |
| Model call error rate by model | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.operation.duration_count", "gen_ai.operation.name"=~"chat\|generate_content\|text_completion", "error.type"!=""}[5m])) / sum by ("gen_ai.request.model") (increase({"gen_ai.client.operation.duration_count", "gen_ai.operation.name"=~"chat\|generate_content\|text_completion"}[5m]))` | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.inference.duration_count", "error.type"!=""}[5m])) / sum by ("gen_ai.request.model") (increase({"gen_ai.client.inference.duration_count"}[5m]))` |
| Input tokens spent | `sum(increase({"gen_ai.client.token.usage_sum", "gen_ai.token.type"="input"}[5m]))` | `sum(increase({"gen_ai.client.inference.usage.input_tokens_total"}[5m]))` |
| Output tokens spent | `sum(increase({"gen_ai.client.token.usage_sum", "gen_ai.token.type"="output"}[5m]))` | `sum(increase({"gen_ai.client.inference.usage.output_tokens_total"}[5m]))` |
| Tokens spent by model | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.token.usage_sum"}[5m]))` | `sum by ("gen_ai.request.model") (increase({"gen_ai.client.inference.usage.input_tokens_total"}[5m])) + sum by ("gen_ai.request.model") (increase({"gen_ai.client.inference.usage.output_tokens_total"}[5m]))` |
| Cache hit ratio (cached vs. total input tokens) | Not available as a metric. Only from `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.input_tokens` span attributes. | `sum(increase({"gen_ai.client.inference.usage.cache_read.input_tokens_total"}[5m])) / sum(increase({"gen_ai.client.inference.usage.input_tokens_total"}[5m]))` |
| Agent invocation rate and error rate by agent | From internal `invoke_agent` spans only. | `sum by ("gen_ai.agent.name") (rate({"gen_ai.invoke_agent.duration_count"}[5m]))`; filter on `"error.type"!=""` for errors. |
| Agent invocation latency p95 by agent | From internal `invoke_agent` span durations only. | `histogram_quantile(0.95, sum by ("le", "gen_ai.agent.name") (rate({"gen_ai.invoke_agent.duration_bucket"}[5m])))` |
| Workflow latency p95 | From `invoke_workflow` spans only. | `histogram_quantile(0.95, sum by ("le") (rate({"gen_ai.invoke_workflow.duration_bucket"}[5m])))` |
| Tool call rate and error rate by tool | From `execute_tool` spans only. | `sum by ("gen_ai.tool.name") (rate({"gen_ai.execute_tool.duration_count"}[5m]))`; filter on `"error.type"!=""` for errors. |
| Tool call latency p95 by tool | From `execute_tool` span durations only. | `histogram_quantile(0.95, sum by ("le", "gen_ai.tool.name") (rate({"gen_ai.execute_tool.duration_bucket"}[5m])))` |
| Model and tool calls per agent invocation | Not available. | `gen_ai.invoke_agent.inference_calls` and `gen_ai.invoke_agent.tool_calls` histograms. |

## Summary of changes

### Inference span and event attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.usage.cache_creation.input_tokens` &rarr; `gen_ai.usage.cache_write.input_tokens` | [#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440) | |
| `gen_ai.request.top_k` | [#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217) | Type changed from `double` to `int`; decoding only. |
| `gen_ai.system_instructions` | [#257](https://github.com/open-telemetry/semantic-conventions-genai/pull/257) | Limited to text parts. |
| `gen_ai.output.messages[].finish_reason` | [#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363) | Deprecated, use `gen_ai.response.finish_reasons`. |

References:

- [Model spans v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-spans.md)
- [Model spans (latest)](/docs/gen-ai/gen-ai-spans.md)

### Retrieval span attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.request.top_k` &rarr; `gen_ai.retrieval.top_k` | [#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217) | Type `int`. |

### Invoke agent internal span attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.agent.id` | [#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242) | Removed. |
| `gen_ai.agent.version` | [#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322) | Removed. |
| `gen_ai.provider.name` | [#289](https://github.com/open-telemetry/semantic-conventions-genai/pull/289) | Removed. |
| `gen_ai.usage.cache_read.input_tokens` | [#469](https://github.com/open-telemetry/semantic-conventions-genai/pull/469) | Removed. |
| `gen_ai.usage.cache_creation.input_tokens` | [#469](https://github.com/open-telemetry/semantic-conventions-genai/pull/469) | Removed. |

References:

- [Agent spans v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-agent-spans.md)
- [Agent spans (latest)](/docs/gen-ai/gen-ai-agent-spans.md)

### Invoke agent client and create agent span attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.agent.id` | [#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242) | Now a stable hosted-agent identifier. Don't use transient instance IDs. |

### Inference span type

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.inference.client` &rarr; `gen_ai.client.inference` | [#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521) | Provider refinements follow `<provider>.gen_ai.client.inference`. Not visible in telemetry until span types are exported over OTLP. |

### GenAI client inference duration metric

Metric changes:

- **Name**: `gen_ai.client.operation.duration` &rarr; `gen_ai.client.inference.duration`
  for inference operations ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))
- **Attributes**: no change
- `gen_ai.client.operation.duration` remains for other GenAI client operations
  and SHOULD NOT be reported for inference
  ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))

References:

- [Metric `gen_ai.client.operation.duration` v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationduration)
- [Client inference (latest)](/docs/gen-ai/client-inference.md)

### GenAI client streaming metrics

Metric changes:

- **Name**: `gen_ai.client.operation.time_to_first_chunk` &rarr;
  `gen_ai.client.inference.time_to_first_chunk`
  ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))
- **Name**: `gen_ai.client.operation.time_per_output_chunk` &rarr;
  `gen_ai.client.inference.time_per_output_chunk`
  ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))
- **Attributes**: no change

References:

- [Metric `gen_ai.client.operation.time_to_first_chunk` v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationtime_to_first_chunk)
- [Client inference (latest)](/docs/gen-ai/client-inference.md)

### GenAI client token usage metric

Metric changes:

- **Name**: `gen_ai.client.token.usage` removed and replaced by the metrics
  below ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))
- **Attributes**: `gen_ai.token.type` removed; new `gen_ai.token.modality`
  on usage counters ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))

| Metric | Instrument | Replaces |
| --- | --- | --- |
| `gen_ai.client.inference.usage.input_tokens` | Counter | `gen_ai.client.token.usage` `_sum` with `gen_ai.token.type="input"` |
| `gen_ai.client.inference.usage.output_tokens` | Counter | `gen_ai.client.token.usage` `_sum` with `gen_ai.token.type="output"` |
| `gen_ai.client.inference.usage.cache_read.input_tokens` | Counter | New |
| `gen_ai.client.inference.usage.cache_write.input_tokens` | Counter | New |
| `gen_ai.client.inference.usage.reasoning.output_tokens` | Counter | New |
| `gen_ai.client.inference.operation.input_tokens` | Histogram | `gen_ai.client.token.usage` with `gen_ai.token.type="input"` |
| `gen_ai.client.inference.operation.output_tokens` | Histogram | `gen_ai.client.token.usage` with `gen_ai.token.type="output"` |

References:

- [Metric `gen_ai.client.token.usage` v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclienttokenusage)
- [Inference token metrics (latest)](/docs/gen-ai/gen-ai-token-metrics.md)

### New agent, workflow, and tool metrics

| Metric | PR | Comments |
| --- | --- | --- |
| New: `gen_ai.invoke_agent.duration` | [#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201), [#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322) | |
| New: `gen_ai.execute_tool.duration` | [#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201), [#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322) | |
| New: `gen_ai.invoke_workflow.duration` | [#126](https://github.com/open-telemetry/semantic-conventions-genai/pull/126), [#341](https://github.com/open-telemetry/semantic-conventions-genai/pull/341) | |
| New: `gen_ai.invoke_agent.inference_calls` | [#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336) | |
| New: `gen_ai.invoke_agent.tool_calls` | [#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336) | |

References:

- [GenAI metrics (latest)](/docs/gen-ai/gen-ai-metrics.md)
