<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Ollama
--->

# Semantic conventions for Ollama client operations

**Status**: [Development][DocumentStatus]

<!-- toc -->

- [Overview](#overview)
- [Provider and operation mapping](#provider-and-operation-mapping)
- [Request options mapping](#request-options-mapping)
- [Response mapping](#response-mapping)
- [Spans](#spans)
  - [Inference](#inference)
  - [Embeddings](#embeddings)
- [Ollama-specific attributes](#ollama-specific-attributes)

<!-- tocstop -->

The Semantic Conventions for [Ollama](https://ollama.com/) extend and override the [GenAI Semantic Conventions](README.md).

## Overview

[Ollama](https://ollama.com/) is an open-source runtime for serving large language models locally.

Ollama calls use the standard GenAI client spans; no Ollama-specific span types are defined.
`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

## Provider and operation mapping

| Ollama endpoint | Span type | `gen_ai.operation.name` |
| --- | --- | --- |
| `/api/chat` | `gen_ai.client.inference` | `chat` |
| `/api/generate` | `gen_ai.client.inference` | `text_completion` |
| `/api/embed` | `gen_ai.client.embeddings` | `embeddings` |

The `/api/generate` endpoint maps to `gen_ai.client.inference` with
`gen_ai.operation.name = "text_completion"`. The shared conformance mock server
implements `/api/chat` and `/api/embed` only, so the reference scenario serves a
canned `/api/generate` response from a scenario-local HTTP server to exercise the
endpoint.

Tool calling is supported by the `/api/chat` endpoint, with the tool itself running in
application code: `execute_tool` operations are not instrumented at the client boundary.
Offered tools are recorded as `gen_ai.tool.definitions`, and a tool call the model returns
is recorded as `tool_call` parts of the output message; Ollama tool calls carry no
identifier, which the output message parts permit. `gen_ai.tool.definitions` is an
opt-in attribute: tool schemas may be large and may contain sensitive information, so
instrumentations SHOULD record it only when the application opts in to tool-definition
capture, following the registry note for the attribute.

## Request options mapping

Ollama carries sampling options in the request's `options` object rather than as top-level
fields. Instrumentations SHOULD map them to the generic GenAI request attributes:

| Ollama option | GenAI attribute |
| --- | --- |
| `num_predict` | `gen_ai.request.max_tokens` |
| `temperature` | `gen_ai.request.temperature` |
| `top_p` | `gen_ai.request.top_p` |
| `top_k` | `gen_ai.request.top_k` |
| `frequency_penalty` | `gen_ai.request.frequency_penalty` |
| `presence_penalty` | `gen_ai.request.presence_penalty` |
| `stop` | `gen_ai.request.stop_sequences` |
| `seed` | `gen_ai.request.seed` |

Ollama uses negative `num_predict` values as sentinels rather than token limits, for
example `-1` to request unlimited generation. Instrumentations SHOULD omit
`gen_ai.request.max_tokens` for negative `num_predict` values instead of reporting a
negative maximum.

Ollama-specific options with no generic equivalent, such as `num_ctx`, are recorded with
the `ollama.request.*` attributes defined below.

The `/api/chat` endpoint also accepts a top-level `format` argument that requests a
specific output format, for example `format = "json"` or a JSON schema object. It is not
part of the `options` object; instrumentations SHOULD record the requested output type as
`gen_ai.output.type = "json"` when the request includes it, per the conditionally required
`gen_ai.output.type` attribute.

## Response mapping

The native Ollama response fields map to the generic GenAI attributes:

| Ollama response field | GenAI attribute |
| --- | --- |
| `prompt_eval_count` | `gen_ai.usage.input_tokens` |
| `prompt_eval_cached_count` | `gen_ai.usage.cache_read.input_tokens` |
| `eval_count` | `gen_ai.usage.output_tokens` |
| `done_reason` | `gen_ai.response.finish_reasons` (single-element array) |
| `model` | `gen_ai.response.model` |

Ollama servers since 0.33.3 also report `prompt_eval_cached_count`, the number of prompt
tokens served from the prompt cache. It is a subset of `prompt_eval_count`, consistent
with the generic convention that `gen_ai.usage.cache_read.input_tokens` is included in
`gen_ai.usage.input_tokens`. `ollama-python` does not expose the field as of 0.6.3, so
the reference scenario cannot demonstrate the mapping; instrumentations with access to
the raw response SHOULD record it as `gen_ai.usage.cache_read.input_tokens` when the
server reports a non-zero value, following the requirement level of the generic
attribute. Like the other usage counts, the field appears on the final chunk of a
streaming response.

The `total_duration` and `load_duration` response timings have no generic equivalent and
are recorded with `ollama.response.total_duration` and `ollama.response.load_duration`.
Distinguishing model load time from generation time is useful for capacity planning on
self-hosted deployments, where models are loaded on demand.

For streaming chat requests, `gen_ai.request.stream` and `gen_ai.response.time_to_first_chunk`
follow the generic GenAI client conventions; the usage counts and the `total_duration` and
`load_duration` timings are read from the final chunk of the stream.

## Spans

Ollama refines the standard GenAI client spans with the Ollama-specific attributes
defined below. The tables list the recording requirements for each refinement; all
other attributes follow the base span conventions.

### Inference

`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

<!-- weaver .refinements.spans[] | select(.id == "ollama.gen_ai.client.inference") | .attributes |= map(select(.key != "gen_ai.provider.name")) -->
<!-- endweaver -->

### Embeddings

`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

<!-- weaver .refinements.spans[] | select(.id == "ollama.gen_ai.client.embeddings") | .attributes |= map(select(.key != "gen_ai.provider.name")) -->
<!-- endweaver -->

## Ollama-specific attributes

Ollama-specific attributes capture request options and response metrics that are unique to
the Ollama platform and have no generic GenAI equivalent. They are defined in the
[Ollama attribute registry](/docs/registry/attributes/ollama.md) and recorded as refinements
of the standard [GenAI client inference](client-inference.md) and
[GenAI client embeddings](client-embeddings.md) span conventions when
`gen_ai.provider.name` is `"ollama"`.

- `ollama.request.base_url`: the base URL of the Ollama API endpoint, recorded without
  user information (credentials) or sensitive query values. Beyond `server.address` and
  `server.port`, the base URL carries the scheme (plain HTTP versus TLS) and any path
  prefix, for example the route of a reverse proxy in front of the instance, which the
  server attributes do not record.
- `ollama.request.num_ctx`: the size of the context window for the model.
- `ollama.request.num_batch`: the number of tokens to process in parallel.
- `ollama.request.num_gpu`: the number of model layers to offload to GPUs for inference.
- `ollama.request.main_gpu`: the index of the main GPU to use.
- `ollama.response.total_duration`: the total time in nanoseconds the model took to generate the response.
- `ollama.response.load_duration`: the time in nanoseconds the model took to load.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
