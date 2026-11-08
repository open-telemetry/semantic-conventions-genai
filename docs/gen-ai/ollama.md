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

## Request options mapping

Ollama carries sampling options in the request's `options` object rather than as top-level
fields. Instrumentations SHOULD map them to the generic GenAI request attributes:

| Ollama option | GenAI attribute |
| --- | --- |
| `num_predict` | `gen_ai.request.max_tokens` |
| `temperature` | `gen_ai.request.temperature` |
| `top_p` | `gen_ai.request.top_p` |
| `top_k` | `gen_ai.request.top_k` |
| `stop` | `gen_ai.request.stop_sequences` |
| `seed` | `gen_ai.request.seed` |

Ollama-specific options with no generic equivalent, such as `num_ctx`, are recorded with
the `ollama.request.*` attributes defined below.

## Response mapping

The native Ollama response fields map to the generic GenAI attributes:

| Ollama response field | GenAI attribute |
| --- | --- |
| `prompt_eval_count` | `gen_ai.usage.input_tokens` |
| `eval_count` | `gen_ai.usage.output_tokens` |
| `done_reason` | `gen_ai.response.finish_reasons` (single-element array) |
| `model` | `gen_ai.response.model` |

The `total_duration` and `load_duration` response timings have no generic equivalent and
are recorded with `ollama.response.total_duration` and `ollama.response.load_duration`.
Distinguishing model load time from generation time is useful for capacity planning on
self-hosted deployments, where models are loaded on demand.

## Ollama-specific attributes

Ollama-specific attributes capture request options and response metrics that are unique to
the Ollama platform and have no generic GenAI equivalent. They are defined in the
[Ollama attribute registry](/docs/registry/attributes/ollama.md) and follow the standard
[GenAI client inference](client-inference.md) and [GenAI client embeddings](client-embeddings.md)
span conventions.

- `ollama.request.base_url`: the base URL of the Ollama API endpoint.
- `ollama.request.num_ctx`: the size of the context window for the model.
- `ollama.request.num_batch`: the number of tokens to process in parallel.
- `ollama.request.num_gpu`: the number of GPUs to use for inference.
- `ollama.request.main_gpu`: the index of the main GPU to use.
- `ollama.request.low_vram`: whether to use low VRAM mode.
- `ollama.request.f16_kv`: whether to use 16-bit floating point for the key-value cache.
- `ollama.response.total_duration`: the total time in nanoseconds the model took to generate the response.
- `ollama.response.load_duration`: the time in nanoseconds the model took to load.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
