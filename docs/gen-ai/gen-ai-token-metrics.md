<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Token Metrics
--->

# Semantic conventions for generative AI inference token metrics

**Status**: [Development][DocumentStatus]

<!-- toc -->

- [Semantic conventions for generative AI inference token metrics](#semantic-conventions-for-generative-ai-inference-token-metrics)
  - [How to aggregate token usage](#how-to-aggregate-token-usage)
  - [Inference token metrics](#inference-token-metrics)
    - [Metric: `gen_ai.client.inference.usage.input_tokens`](#metric-gen_aiclientinferenceusageinput_tokens)
    - [Metric: `gen_ai.client.inference.usage.output_tokens`](#metric-gen_aiclientinferenceusageoutput_tokens)
    - [Metric: `gen_ai.client.inference.usage.cache_read.input_tokens`](#metric-gen_aiclientinferenceusagecache_readinput_tokens)
    - [Metric: `gen_ai.client.inference.usage.cache_write.input_tokens`](#metric-gen_aiclientinferenceusagecache_writeinput_tokens)
    - [Metric: `gen_ai.client.inference.usage.reasoning.output_tokens`](#metric-gen_aiclientinferenceusagereasoningoutput_tokens)
    - [Metric: `gen_ai.client.inference.operation.input_tokens`](#metric-gen_aiclientinferenceoperationinput_tokens)
    - [Metric: `gen_ai.client.inference.operation.output_tokens`](#metric-gen_aiclientinferenceoperationoutput_tokens)
<!-- tocstop -->

## How to aggregate token usage

> [!NOTE]
> Use [inference token metrics](#inference-token-metrics) (or corresponding
> [embeddings](client-embeddings.md#metrics) or other metrics, depending on the
> operation) whenever possible. They aren't affected by trace sampling. Filter
> or group by `service.name` if multiple services report the same operations.

To see token usage in an individual trace, filter by `gen_ai.operation.name`
and break down by `service.name` if multiple services report the same type of
spans. For example (pseudocode):

<!-- TODO: replace the gen_ai.operation.name filter with
span.type, see
https://github.com/open-telemetry/opentelemetry-specification/pull/5378 -->

```text
sum(gen_ai.usage.input_tokens)
  where trace_id == "<trace id>"
    and gen_ai.operation.name in (chat, generate_content, text_completion, realtime_inference)
  group by service.namespace, service.name
```

> [!WARNING]
> Don't sum `gen_ai.usage.*` over all spans without filtering by operation name.
> The same tokens can be reported on multiple types of spans: agent and
> inference spans, or inference spans from gateways and different layers of
> the inference infrastructure.

## Inference token metrics

The conventions described in this document are specific to Generative AI client
applications and describe how inference token metrics are reported.

Individual systems may include additional system-specific attributes.
It is recommended to check system-specific documentation, if available.

Two families of token instruments are defined:

- **Usage** (`gen_ai.client.inference.usage.*` counters) are the primary instruments
  for measuring token consumption. They track how many tokens were spent over time, spending rate,
  and serve as a proxy for cost approximation. Each token category is a separate
  monotonic counter broken down by [`gen_ai.token.modality`](/docs/registry/attributes/gen-ai.md),
  except `gen_ai.client.inference.usage.reasoning.output_tokens`.
  The `cache_read`,
  `cache_write`, and `reasoning` counters report subsets of the `input_tokens`
  and `output_tokens` counters.
- **Per-operation token distribution** (`gen_ai.client.inference.operation.input_tokens`
  and `gen_ai.client.inference.operation.output_tokens`) describe how token usage
  is distributed across individual inference operations. They should not be used
  for total usage or cost calculations. Use histograms exclusively to monitor
  usage percentiles (e.g. p95/p99) and detect outliers.

Embeddings operations only report the
[`gen_ai.client.embeddings.operation.input_tokens`](client-embeddings.md#metric-gen_aiclientembeddingsoperationinput_tokens)
histogram, and total token usage can be computed from it.

> [!NOTE]
> 
> The `gen_ai.client.inference.operation.input_tokens` and
> `gen_ai.client.inference.operation.output_tokens` histograms are
> deliberately not broken down by modality: percentiles across modalities do
> not add up.
> 
> A query like this one appears valid:
> 
> ```promql
> histogram_quantile(0.95,
>   sum(rate({"gen_ai.client.inference.operation.input_tokens"}[5m]))
> )
> ```
> 
> However, if modality were added as a dimension, it would produce meaningless results: for
> 100 identical operations with 300 input tokens each (100 text and 200 image),
> it would return 200 instead of 300.
> 
> For the full reasoning behind this design, see
> [Token metrics design](/docs/gen-ai/non-normative/token-metrics-design.md).

### Metric: `gen_ai.client.inference.usage.input_tokens`

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.usage.input_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.usage.input_tokens` | Counter | `{token}` | The number of input (prompt) tokens used, including cached tokens. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** This metric SHOULD be reported for non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) when the operation involves the usage of tokens and the count is readily available, and SHOULD NOT be reported for `realtime_inference` or other operations.
When systems report both used tokens and billable tokens, instrumentation MUST report billable tokens.
See `gen_ai.token.modality` attribute for how to split tokens by modality.
Instrumentation SHOULD record contributions from successful and failed inference operations. Each measurement MUST be a known, strictly positive modality contribution.
When a contribution's modality cannot reliably be determined, instrumentation MUST set `gen_ai.token.modality` to `unknown`.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`gen_ai.token.modality`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The modality of the tokens being counted. [3] | `text`; `image`; `audio` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `gen_ai.token.modality`:** For each operation, token usage counter measurements across all modalities
SHOULD add up to the corresponding total, such as the `gen_ai.usage.input_tokens`
attribute or a measurement on the `gen_ai.client.inference.operation.input_tokens`
histogram.

Instrumentations SHOULD record tokens as `unknown` when their modality
cannot reliably be determined. For example, if a
provider reports 300 input tokens and 100 of them are audio, record 100 as
`audio` and 200 as `unknown`.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

---

`gen_ai.token.modality` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `audio` | Audio tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `image` | Image tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `text` | Text tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `unknown` | The modality is not known. | ![Development](https://img.shields.io/badge/-development-blue) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.usage.output_tokens`

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.usage.output_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.usage.output_tokens` | Counter | `{token}` | The number of output (completion) tokens used, including reasoning tokens. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** This metric SHOULD be reported for non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) when the operation involves the usage of tokens and the count is readily available, and SHOULD NOT be reported for `realtime_inference` or other operations.
When systems report both used tokens and billable tokens, instrumentation MUST report billable tokens.
See `gen_ai.token.modality` attribute for how to split tokens by modality.
Instrumentation SHOULD record contributions from successful and failed inference operations. Each measurement MUST be a known, strictly positive modality contribution.
When a contribution's modality cannot reliably be determined, instrumentation MUST set `gen_ai.token.modality` to `unknown`.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`gen_ai.token.modality`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The modality of the tokens being counted. [3] | `text`; `image`; `audio` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `gen_ai.token.modality`:** For each operation, token usage counter measurements across all modalities
SHOULD add up to the corresponding total, such as the `gen_ai.usage.input_tokens`
attribute or a measurement on the `gen_ai.client.inference.operation.input_tokens`
histogram.

Instrumentations SHOULD record tokens as `unknown` when their modality
cannot reliably be determined. For example, if a
provider reports 300 input tokens and 100 of them are audio, record 100 as
`audio` and 200 as `unknown`.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

---

`gen_ai.token.modality` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `audio` | Audio tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `image` | Image tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `text` | Text tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `unknown` | The modality is not known. | ![Development](https://img.shields.io/badge/-development-blue) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.usage.cache_read.input_tokens`

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.usage.cache_read.input_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.usage.cache_read.input_tokens` | Counter | `{token}` | The number of input tokens served from a provider-managed cache. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** Applies only to non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) and SHOULD NOT be reported for `realtime_inference` or other operations.
This value is a subset of `gen_ai.client.inference.usage.input_tokens`.
Instrumentation SHOULD record contributions from successful and failed inference operations. Each measurement MUST be a known, strictly positive modality contribution.
When a contribution's modality cannot reliably be determined, instrumentation MUST set `gen_ai.token.modality` to `unknown`.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`gen_ai.token.modality`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The modality of the tokens being counted. [3] | `text`; `image`; `audio` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `gen_ai.token.modality`:** For each operation, token usage counter measurements across all modalities
SHOULD add up to the corresponding total, such as the `gen_ai.usage.input_tokens`
attribute or a measurement on the `gen_ai.client.inference.operation.input_tokens`
histogram.

Instrumentations SHOULD record tokens as `unknown` when their modality
cannot reliably be determined. For example, if a
provider reports 300 input tokens and 100 of them are audio, record 100 as
`audio` and 200 as `unknown`.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

---

`gen_ai.token.modality` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `audio` | Audio tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `image` | Image tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `text` | Text tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `unknown` | The modality is not known. | ![Development](https://img.shields.io/badge/-development-blue) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.usage.cache_write.input_tokens`

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.usage.cache_write.input_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.usage.cache_write.input_tokens` | Counter | `{token}` | The number of input tokens written to a provider-managed cache. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** Applies only to non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) and SHOULD NOT be reported for `realtime_inference` or other operations.
This value is a subset of `gen_ai.client.inference.usage.input_tokens`.
Instrumentation SHOULD record contributions from successful and failed inference operations. Each measurement MUST be a known, strictly positive modality contribution.
When a contribution's modality cannot reliably be determined, instrumentation MUST set `gen_ai.token.modality` to `unknown`.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`gen_ai.token.modality`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The modality of the tokens being counted. [3] | `text`; `image`; `audio` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `gen_ai.token.modality`:** For each operation, token usage counter measurements across all modalities
SHOULD add up to the corresponding total, such as the `gen_ai.usage.input_tokens`
attribute or a measurement on the `gen_ai.client.inference.operation.input_tokens`
histogram.

Instrumentations SHOULD record tokens as `unknown` when their modality
cannot reliably be determined. For example, if a
provider reports 300 input tokens and 100 of them are audio, record 100 as
`audio` and 200 as `unknown`.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

---

`gen_ai.token.modality` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `audio` | Audio tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `image` | Image tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `text` | Text tokens. | ![Development](https://img.shields.io/badge/-development-blue) |
| `unknown` | The modality is not known. | ![Development](https://img.shields.io/badge/-development-blue) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.usage.reasoning.output_tokens`

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.usage.reasoning.output_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.usage.reasoning.output_tokens` | Counter | `{token}` | The number of output tokens used for reasoning (e.g. chain-of-thought, extended thinking). [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** Applies only to non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) and SHOULD NOT be reported for `realtime_inference` or other operations.
This value is a subset of `gen_ai.client.inference.usage.output_tokens`.
Instrumentation SHOULD record contributions from successful and failed inference operations. Each measurement MUST be a known, strictly positive reasoning token count.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [3] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [4] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [5] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [6] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[4] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[5] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[6] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [7] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[7]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[8]:** May be used when specific backend is unknown.

**[9]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.operation.input_tokens`

This metric SHOULD be specified with [ExplicitBucketBoundaries] of [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864].

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.operation.input_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.operation.input_tokens` | Histogram | `{token}` | The number of input (prompt) tokens used per inference operation. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** This metric SHOULD be reported for non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) when the operation involves the usage of tokens and the count is readily available, and SHOULD NOT be reported for `realtime_inference` or other operations.
For example, if GenAI system returns usage information in the streaming response, it SHOULD be used. Or if GenAI system returns each token independently, instrumentation SHOULD count number of output tokens and record the result.
If instrumentation cannot efficiently obtain number of input and/or output tokens, it MAY allow users to enable offline token counting. Otherwise it MUST NOT report usage metrics.
When systems report both used tokens and billable tokens, instrumentation MUST report billable tokens.
Instrumentations SHOULD record this metric for each inference operation, including failed ones. The recorded value SHOULD match the token count returned by the provider, or `0` if the response was not received or did not contain token usage.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`error.type`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/error.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If the operation ended in an error. | string | Describes a class of error the operation ended with. [3] | `timeout`; `java.net.UnknownHostException`; `server_certificate_invalid`; `500` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `error.type`:** The `error.type` SHOULD match the error code returned by the Generative AI provider or the client library,
the canonical name of exception that occurred, or another low-cardinality error identifier.
Instrumentations SHOULD document the list of errors they report.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`error.type` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `_OTHER` | A fallback error value to be used when the instrumentation doesn't define a custom value. | ![Stable](https://img.shields.io/badge/-stable-lightgreen) |

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Metric: `gen_ai.client.inference.operation.output_tokens`


This metric SHOULD be specified with [ExplicitBucketBoundaries] of [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864].

<!-- weaver .registry.metrics[] | select(.name == "gen_ai.client.inference.operation.output_tokens") -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

| Name | Instrument Type | Unit (UCUM) | Description | Stability | Entity Associations |
| -------- | --------------- | ----------- | -------------- | --------- | ------ |
| `gen_ai.client.inference.operation.output_tokens` | Histogram | `{token}` | The number of output (completion) tokens used per inference operation. [1] | ![Development](https://img.shields.io/badge/-development-blue) | |

**[1]:** This metric SHOULD be reported for non-realtime client inference operations (`chat`, `generate_content`, `text_completion`) when the operation involves the usage of tokens and the count is readily available, and SHOULD NOT be reported for `realtime_inference` or other operations.
For example, if GenAI system returns usage information in the streaming response, it SHOULD be used. Or if GenAI system returns each token independently, instrumentation SHOULD count number of output tokens and record the result.
If instrumentation cannot efficiently obtain number of input and/or output tokens, it MAY allow users to enable offline token counting. Otherwise it MUST NOT report usage metrics.
When systems report both used tokens and billable tokens, instrumentation MUST report billable tokens.
Instrumentations SHOULD record this metric for each inference operation, including failed ones. The recorded value SHOULD match the token count returned by the provider, or `0` if the response was not received or did not contain token usage.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `text_completion` |
| [`gen_ai.provider.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The Generative AI provider as identified by the client or server instrumentation. [2] | `openai`; `gcp.gen_ai`; `gcp.vertex_ai` |
| [`error.type`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/error.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If the operation ended in an error. | string | Describes a class of error the operation ended with. [3] | `timeout`; `java.net.UnknownHostException`; `server_certificate_invalid`; `500` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [4] | `gpt-4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [5] | `80`; `8080`; `443` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `gpt-4-0613` |
| [`gen_ai.response.service_tier`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The service tier that processed the inference operation. [6] | `default`; `priority`; `ON_DEMAND` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [7] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be one of `chat`, `generate_content`, or `text_completion`.

**[2] `gen_ai.provider.name`:** Semantic conventions for individual GenAI operations SHOULD clarify which
kinds of providers (e.g. inference, embeddings, retrieval, memory, hosted
agent providers) apply when it is not clear from context.

The attribute SHOULD be set based on the instrumentation's best knowledge
and may differ from the actual upstream provider. For example, a client SDK
may be configured against a proxy or hosting platform that transparently
relays requests to a different provider.

The `gen_ai.provider.name` attribute acts as a discriminator that
identifies the GenAI telemetry format flavor specific to that provider
within GenAI semantic conventions.
It SHOULD be set consistently with provider-specific attributes and signals.
For example, GenAI spans, metrics, and events related to AWS Bedrock
should have the `gen_ai.provider.name` set to `aws.bedrock` and include
applicable `aws.bedrock.*` attributes and are not expected to include
`openai.*` attributes.

**[3] `error.type`:** The `error.type` SHOULD match the error code returned by the Generative AI provider or the client library,
the canonical name of exception that occurred, or another low-cardinality error identifier.
Instrumentations SHOULD document the list of errors they report.

**[4] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[5] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[6] `gen_ai.response.service_tier`:** The value SHOULD be the one returned by the provider. It can differ from
`gen_ai.request.service_tier` when `auto` is requested.
For example, `service_tier` in [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
`usage.service_tier` in [Anthropic](https://platform.claude.com/docs/en/api/service-tiers),
or [`usageMetadata.trafficType`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse#UsageMetadata.FIELDS.traffic_type) in Vertex AI.

**[7] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

---

`error.type` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `_OTHER` | A fallback error value to be used when the instrumentation doesn't define a custom value. | ![Stable](https://img.shields.io/badge/-stable-lightgreen) |

---

`gen_ai.provider.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `anthropic` | [Anthropic](https://www.anthropic.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `aws.bedrock` | [AWS Bedrock](https://aws.amazon.com/bedrock) | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.inference` | Azure AI Inference | ![Development](https://img.shields.io/badge/-development-blue) |
| `azure.ai.openai` | [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview) | ![Development](https://img.shields.io/badge/-development-blue) |
| `cohere` | [Cohere](https://cohere.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `deepseek` | [DeepSeek](https://www.deepseek.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gemini` | [Gemini](https://cloud.google.com/products/gemini) [8] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.gen_ai` | Any Google generative AI endpoint [9] | ![Development](https://img.shields.io/badge/-development-blue) |
| `gcp.vertex_ai` | [Vertex AI](https://cloud.google.com/vertex-ai) [10] | ![Development](https://img.shields.io/badge/-development-blue) |
| `groq` | [Groq](https://groq.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ibm.watsonx.ai` | [IBM Watsonx AI](https://www.ibm.com/products/watsonx-ai) | ![Development](https://img.shields.io/badge/-development-blue) |
| `mistral` | [Mistral](https://mistral.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `moonshot_ai` | [Moonshot AI](https://www.moonshot.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `ollama` | [Ollama](https://ollama.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `openai` | [OpenAI](https://openai.com/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `perplexity` | [Perplexity](https://www.perplexity.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |
| `x_ai` | [xAI](https://x.ai/) | ![Development](https://img.shields.io/badge/-development-blue) |

**[8]:** Used when accessing the 'generativelanguage.googleapis.com' endpoint. Also known as the AI Studio API.

**[9]:** May be used when specific backend is unknown.

**[10]:** Used when accessing the 'aiplatform.googleapis.com' endpoint.

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
[ExplicitBucketBoundaries]: https://github.com/open-telemetry/opentelemetry-specification/blob/v1.55.0/specification/metrics/api.md#instrument-advisory-parameters
