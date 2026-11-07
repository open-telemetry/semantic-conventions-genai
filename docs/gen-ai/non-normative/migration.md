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
| Embeddings latency p95 by model | `histogram_quantile(0.95, sum by ("le", "gen_ai.request.model") (rate({"gen_ai.client.operation.duration_bucket", "gen_ai.operation.name"="embeddings"}[5m])))` | `histogram_quantile(0.95, sum by ("le", "gen_ai.request.model") (rate({"gen_ai.client.embeddings.duration_bucket"}[5m])))` |
| Embeddings input tokens | `sum(increase({"gen_ai.client.token.usage_sum", "gen_ai.operation.name"="embeddings"}[5m]))` | `sum(increase({"gen_ai.client.embeddings.operation.input_tokens_sum"}[5m]))` |
| Remote agent invocation latency p95 by agent | `histogram_quantile(0.95, sum by ("le") (rate({"gen_ai.client.operation.duration_bucket", "gen_ai.operation.name"="invoke_agent"}[5m])))` | `histogram_quantile(0.95, sum by ("le", "gen_ai.agent.name") (rate({"gen_ai.client.invoke_agent.duration_bucket"}[5m])))` |
| Agent invocation rate and error rate by agent | From internal `invoke_agent` spans only. | `sum by ("gen_ai.agent.name") (rate({"gen_ai.invoke_agent.duration_count", "gen_ai.operation.name"="invoke_agent"}[5m]))`; filter on `"error.type"!=""` for errors. |
| Agent invocation latency p95 by agent | From internal `invoke_agent` span durations only. | `histogram_quantile(0.95, sum by ("le", "gen_ai.agent.name") (rate({"gen_ai.invoke_agent.duration_bucket", "gen_ai.operation.name"="invoke_agent"}[5m])))` |
| Workflow latency p95 by workflow | From `invoke_workflow` spans only. | `histogram_quantile(0.95, sum by ("le", "gen_ai.agent.name") (rate({"gen_ai.invoke_agent.duration_bucket", "gen_ai.operation.name"="invoke_workflow"}[5m])))` |
| Tool call rate and error rate by tool | From `execute_tool` spans only. | `sum by ("gen_ai.tool.name") (rate({"gen_ai.execute_tool.duration_count"}[5m]))`; filter on `"error.type"!=""` for errors. |
| Tool call latency p95 by tool | From `execute_tool` span durations only. | `histogram_quantile(0.95, sum by ("le", "gen_ai.tool.name") (rate({"gen_ai.execute_tool.duration_bucket"}[5m])))` |
| Retrieval latency p95 | `histogram_quantile(0.95, sum by ("le") (rate({"gen_ai.client.operation.duration_bucket", "gen_ai.operation.name"="retrieval"}[5m])))` | `histogram_quantile(0.95, sum by ("le") (rate({"gen_ai.retrieval.duration_bucket"}[5m])))` for framework retrieval. Use database or other client metrics for calls to retrieval services. |
| Model and tool calls per agent invocation | Not available. | `gen_ai.invoke_agent.inference_calls` and `gen_ai.invoke_agent.tool_calls` histograms. |

## Summary of changes

### All GenAI signals

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.provider.name` value `mistral_ai` &rarr; `mistral` | [#506](https://github.com/open-telemetry/semantic-conventions-genai/pull/506) | |
| Structured content attributes | [#634](https://github.com/open-telemetry/semantic-conventions-genai/pull/634) | Attributes with a JSON schema (for example `gen_ai.input.messages`, `gen_ai.tool.definitions`) are now always structured. The JSON-string fallback on spans is removed. |

### Inference span and event attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.usage.cache_creation.input_tokens` &rarr; `gen_ai.usage.cache_write.input_tokens` | [#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440) | |
| `gen_ai.request.top_k` | [#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217) | Type changed from `double` to `int`; decoding only. |
| `gen_ai.system_instructions` | [#257](https://github.com/open-telemetry/semantic-conventions-genai/pull/257) | Limited to text parts. |
| `gen_ai.output.messages[].finish_reason` | [#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363) | Deprecated, use `gen_ai.response.finish_reasons`. |
| `BlobPart.content` in `gen_ai.input.messages` and `gen_ai.output.messages` | [#144](https://github.com/open-telemetry/semantic-conventions-genai/pull/144) | Now optional. |

References:

- [Model spans v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-spans.md)
- [Client inference (latest)](/docs/gen-ai/client-inference.md)

### Retrieval spans

| Change | PR | Comments |
| --- | --- | --- |
| `retrieval` client span | [#645](https://github.com/open-telemetry/semantic-conventions-genai/pull/645) | Deprecated. Use database or other client conventions for calls to retrieval services, and the new internal `retrieval` span ([#644](https://github.com/open-telemetry/semantic-conventions-genai/pull/644)) for retrieval done by GenAI frameworks and applications. |
| `gen_ai.request.top_k` &rarr; `gen_ai.retrieval.top_k` | [#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217) | Type `int`. |

References:

- [Retrieval (latest)](/docs/gen-ai/retrieval.md)

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

### Invoke workflow span attributes

Workflows follow the internal `invoke_agent` span with `gen_ai.operation.name`
set to `invoke_workflow`
([#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571)).

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.workflow.name` &rarr; `gen_ai.agent.name` | [#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571) | |

### Invoke agent client and create agent span attributes

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.agent.id` | [#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242) | Now a stable hosted-agent identifier. Don't use transient instance IDs. |

References:

- [Client invoke agent (latest)](/docs/gen-ai/client-invoke-agent.md)

### Exception events

`gen_ai.client.operation.exception` is replaced by operation-specific events.
It remains for other GenAI client operations.

| Event | PR | Replaces |
| --- | --- | --- |
| `gen_ai.client.inference.exception` | [#658](https://github.com/open-telemetry/semantic-conventions-genai/pull/658) | `gen_ai.client.operation.exception` for inference |
| `gen_ai.client.embeddings.exception` | [#659](https://github.com/open-telemetry/semantic-conventions-genai/pull/659) | `gen_ai.client.operation.exception` for embeddings |
| `gen_ai.client.invoke_agent.exception` | [#667](https://github.com/open-telemetry/semantic-conventions-genai/pull/667) | `gen_ai.client.operation.exception` for client `invoke_agent` |
| `gen_ai.client.fetch_response.exception` | [#669](https://github.com/open-telemetry/semantic-conventions-genai/pull/669) | New |
| `gen_ai.execute_tool.exception` | [#668](https://github.com/open-telemetry/semantic-conventions-genai/pull/668) | New |
| `gen_ai.invoke_agent.exception` | [#670](https://github.com/open-telemetry/semantic-conventions-genai/pull/670) | New |

References:

- [Exceptions v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-exceptions.md)
- [Exceptions (latest)](/docs/gen-ai/gen-ai-exceptions.md)

### Other events

| Change | PR | Comments |
| --- | --- | --- |
| `gen_ai.client.inference.operation.details` | [#579](https://github.com/open-telemetry/semantic-conventions-genai/pull/579) | Now recommended instead of opt-in. |

### GenAI client operation duration metric

`gen_ai.client.operation.duration` is split into per-operation metrics. It
remains for other GenAI client operations and SHOULD NOT be reported for the
operations below.

| Operation | Metric | PR |
| --- | --- | --- |
| Inference (`chat`, `generate_content`, `text_completion`) | `gen_ai.client.inference.duration` | [#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521) |
| `embeddings` | `gen_ai.client.embeddings.duration` | [#578](https://github.com/open-telemetry/semantic-conventions-genai/pull/578) |
| Client `invoke_agent` | `gen_ai.client.invoke_agent.duration` | [#635](https://github.com/open-telemetry/semantic-conventions-genai/pull/635) |
| `execute_tool` | `gen_ai.execute_tool.duration` | [#636](https://github.com/open-telemetry/semantic-conventions-genai/pull/636) |
| `retrieval` | `gen_ai.retrieval.duration` for framework retrieval; database or other client metrics for retrieval services | [#643](https://github.com/open-telemetry/semantic-conventions-genai/pull/643), [#644](https://github.com/open-telemetry/semantic-conventions-genai/pull/644) |

Attributes are unchanged, except `gen_ai.client.invoke_agent.duration` adds
`gen_ai.agent.name`.

References:

- [Metric `gen_ai.client.operation.duration` v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclientoperationduration)
- [Client inference (latest)](/docs/gen-ai/client-inference.md)
- [Client embeddings (latest)](/docs/gen-ai/client-embeddings.md)
- [Client invoke agent (latest)](/docs/gen-ai/client-invoke-agent.md)
- [Execute tool (latest)](/docs/gen-ai/execute-tool.md)
- [Retrieval (latest)](/docs/gen-ai/retrieval.md)

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
  below ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374),
  [#578](https://github.com/open-telemetry/semantic-conventions-genai/pull/578))
- **Attributes**: `gen_ai.token.type` removed; new `gen_ai.token.modality`
  on usage counters except reasoning tokens
  ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))

| Metric | Instrument | Replaces |
| --- | --- | --- |
| `gen_ai.client.inference.usage.input_tokens` | Counter | `gen_ai.client.token.usage` `_sum` with `gen_ai.token.type="input"` |
| `gen_ai.client.inference.usage.output_tokens` | Counter | `gen_ai.client.token.usage` `_sum` with `gen_ai.token.type="output"` |
| `gen_ai.client.inference.usage.cache_read.input_tokens` | Counter | New |
| `gen_ai.client.inference.usage.cache_write.input_tokens` | Counter | New |
| `gen_ai.client.inference.usage.reasoning.output_tokens` | Counter | New |
| `gen_ai.client.inference.operation.input_tokens` | Histogram | `gen_ai.client.token.usage` with `gen_ai.token.type="input"` for inference |
| `gen_ai.client.inference.operation.output_tokens` | Histogram | `gen_ai.client.token.usage` with `gen_ai.token.type="output"` for inference |
| `gen_ai.client.embeddings.operation.input_tokens` | Histogram | `gen_ai.client.token.usage` with `gen_ai.operation.name="embeddings"` |

References:

- [Metric `gen_ai.client.token.usage` v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-metrics.md#metric-gen_aiclienttokenusage)
- [Inference token metrics (latest)](/docs/gen-ai/gen-ai-token-metrics.md)
- [Client embeddings (latest)](/docs/gen-ai/client-embeddings.md)

### New agent and tool metrics

| Metric | PR | Comments |
| --- | --- | --- |
| New: `gen_ai.invoke_agent.duration` | [#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201), [#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322), [#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571) | Covers agents and workflows; filter on `gen_ai.operation.name`. |
| New: `gen_ai.execute_tool.duration` | [#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201), [#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322) | |
| New: `gen_ai.invoke_agent.inference_calls` | [#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336) | |
| New: `gen_ai.invoke_agent.tool_calls` | [#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336) | |

References:

- [GenAI metrics (latest)](/docs/gen-ai/gen-ai-metrics.md)

### New conventions

Additions with no v1.41.0 equivalent. No migration needed.

| Convention | PR |
| --- | --- |
| `fetch_response` client span | [#353](https://github.com/open-telemetry/semantic-conventions-genai/pull/353) |
| Memory client spans | [#140](https://github.com/open-telemetry/semantic-conventions-genai/pull/140) |
| `plan` internal span | [#97](https://github.com/open-telemetry/semantic-conventions-genai/pull/97) |
| `retrieval` internal span | [#644](https://github.com/open-telemetry/semantic-conventions-genai/pull/644) |
| Skill and command `execute_tool` spans with `gen_ai.skill.*` and `process.*` attributes | [#498](https://github.com/open-telemetry/semantic-conventions-genai/pull/498) |
| Agent transfer `execute_tool` span with `gen_ai.transfer.*` attributes | [#447](https://github.com/open-telemetry/semantic-conventions-genai/pull/447) |
| `invoke_runner` and `invoke_{framework_entrypoint}` operation names on internal `invoke_agent` spans | [#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571) |
| Realtime sessions: `realtime_inference` client and `user_speech` internal spans, `gen_ai.client.realtime_session.started` and `gen_ai.client.realtime_session.ended` events | [#394](https://github.com/open-telemetry/semantic-conventions-genai/pull/394) |
| External content references: `gen_ai.system_instructions_ref`, `gen_ai.input.messages_ref`, `gen_ai.output.messages_ref`, `gen_ai.tool.definitions_ref` | [#490](https://github.com/open-telemetry/semantic-conventions-genai/pull/490) |
| A2A protocol client and server spans | [#195](https://github.com/open-telemetry/semantic-conventions-genai/pull/195) |

References:

- [Execute tool (latest)](/docs/gen-ai/execute-tool.md)
- [Realtime (latest)](/docs/gen-ai/gen-ai-realtime.md)
- [A2A (latest)](/docs/gen-ai/a2a.md)
