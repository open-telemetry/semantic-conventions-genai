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
the reference scenario demonstrates the mapping on a cached prompt-token chat served
by a scenario-local `/api/chat` mock: a capture transport injected into the SDK's
httpx client through the supported `transport` argument reads the field from the raw
response, as instrumentations with access to the raw response SHOULD record it as
`gen_ai.usage.cache_read.input_tokens` when the server reports a non-zero value,
following the requirement level of the generic attribute. The transport is a
workaround: it skips streamed responses so the time-to-first-chunk timing is
preserved, and it is removed once an SDK release exposes the field, which is tracked
in [ollama/ollama-python#773](https://github.com/ollama/ollama-python/issues/773),
with pull requests open to surface it. Like the other usage counts, the field appears
on the final chunk of a streaming response. The reference scenario also counts the cached
tokens on the `gen_ai.client.inference.usage.cache_read.input_tokens`
counter, a subset of the input-token usage counter, per the generic
token metrics.

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
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

**Status:** ![Development](https://img.shields.io/badge/-development-blue)

Semantic Conventions for [Ollama](https://ollama.com/) client spans extend and override the semantic conventions for [Gen AI Spans](gen-ai-spans.md).

`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

**Span name** SHOULD be `{gen_ai.operation.name} {gen_ai.request.model}`.
Semantic conventions for individual GenAI systems and frameworks MAY specify different span name format
and MUST follow the overall [guidelines for span names](https://github.com/open-telemetry/opentelemetry-specification/blob/v1.56.0/specification/trace/api.md#span).

**Span kind** SHOULD be `CLIENT`.

**Span status** SHOULD follow the [Recording Errors](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/recording-errors.md) document.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `chat`; `generate_content`; `realtime_inference` |
| [`error.type`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/error.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If the operation ended in an error. | string | Describes a class of error the operation ended with. [2] | `timeout`; `java.net.UnknownHostException`; `server_certificate_invalid`; `500` |
| [`gen_ai.conversation.id`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` [3] | string | The unique identifier for a conversation (session, thread), used to store and correlate messages within this conversation. [4] | `conv_5j66UpCpwteGg4YSxUnt7lPY` |
| [`gen_ai.output.type`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` [5] | string | Represents the content type requested by the client. [6] | `text`; `json`; `image` |
| [`gen_ai.prompt.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` when a named prompt template is used | string | The name of the prompt that uniquely identifies it. | `analyze-code` |
| [`gen_ai.prompt.version`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` [7] | string | The version of the prompt template used. [8] | `1.0.0`; `2025-05-01`; `prod`; `v2` |
| [`gen_ai.request.choice.count`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available, in the request, and !=1. | int | The target number of candidate completions to return. | `3` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [9] | `gpt-4` |
| [`gen_ai.request.seed`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If applicable and if the request includes a seed. | int | Requests with same seed value more likely to return same result. | `100` |
| [`gen_ai.request.stream`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` [10] | boolean | Indicates whether the GenAI request was made in streaming mode. | |
| [`gen_ai.request.top_k`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If applicable. | int | The top-K sampling setting for the GenAI request: restricts token generation at each step to the K most likely next tokens. [11] | `40` |
| [`ollama.request.main_gpu`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `main_gpu`. | int | The index of the main GPU to use. [12] | `0`; `1` |
| [`ollama.request.num_batch`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_batch`. | int | The number of tokens to process in parallel. [13] | `8`; `16`; `32` |
| [`ollama.request.num_ctx`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_ctx`. | int | The size of the context window for the model. [14] | `2048`; `4096`; `32768` |
| [`ollama.request.num_gpu`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_gpu`. | int | The number of model layers to offload to GPUs for inference. [15] | `1`; `2`; `4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [16] | `80`; `8080`; `443` |
| [`gen_ai.conversation.compacted`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` when available | boolean | Indicates whether the effective conversation context used for this operation is a compacted view of a prior conversation. [17] | `true` |
| [`gen_ai.request.frequency_penalty`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | double | The frequency penalty setting for the GenAI request. | `0.1` |
| [`gen_ai.request.max_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The maximum number of tokens the model generates for a request. | `100` |
| [`gen_ai.request.presence_penalty`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | double | The presence penalty setting for the GenAI request. | `0.1` |
| [`gen_ai.request.previous_response.id`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` [18] | string | The unique identifier of a previous response or interaction used to provide context for the current operation. [19] | `resp_0123456789aBCdef`; `interaction-123` |
| [`gen_ai.request.reasoning.level`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When applicable. | string | The reasoning or thinking effort level requested for a GenAI model. [20] | `low`; `medium`; `high` |
| [`gen_ai.request.stop_sequences`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string[] | List of sequences that the model will use to stop generating further tokens. | `["forest", "lived"]` |
| [`gen_ai.request.temperature`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | double | The temperature setting for the GenAI request. | `0.0` |
| [`gen_ai.request.top_p`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | double | The top_p sampling setting for the GenAI request. | `1.0` |
| [`gen_ai.response.finish_reasons`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string[] | Array of reasons the model stopped generating tokens, corresponding to each generation received. [21] | `["stop"]`; `["stop", "length"]`; `["stop", "length", "error"]` |
| [`gen_ai.response.id`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The identifier for the completion returned in the response. | `chatcmpl-123` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The model name returned in the response. | `gpt-4-0613` |
| [`gen_ai.response.time_to_first_chunk`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` If the request was a streaming request. | double | Time from the start of a logical inference operation to the first chunk in its streaming response, in seconds. [22] | `0.5`; `1.2` |
| [`gen_ai.usage.audio.cache_read.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of audio input tokens served from a provider-managed cache, as reported by the provider for this inference operation. [23] | `60` |
| [`gen_ai.usage.audio.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of audio input tokens, as reported by the provider for this inference operation. [24] | `120` |
| [`gen_ai.usage.audio.output_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of audio output tokens, as reported by the provider for this inference operation. [25] | `240` |
| [`gen_ai.usage.cache_read.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of input tokens served from a provider-managed cache, as reported by the provider for this inference operation. [26] | `50` |
| [`gen_ai.usage.cache_write.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of input tokens written to a provider-managed cache, as reported by the provider for this inference operation. [27] | `25` |
| [`gen_ai.usage.image.cache_read.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of image input tokens served from a provider-managed cache, as reported by the provider for this inference operation. [28] | `128` |
| [`gen_ai.usage.image.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of image input tokens, as reported by the provider for this inference operation. [29] | `258` |
| [`gen_ai.usage.image.output_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of image output tokens, as reported by the provider for this inference operation. [30] | `1290` |
| [`gen_ai.usage.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The number of input tokens reported by the provider for this inference operation. [31] | `100` |
| [`gen_ai.usage.output_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The number of output tokens reported by the provider for this inference operation. [32] | `180` |
| [`gen_ai.usage.reasoning.output_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of output tokens used for reasoning (e.g. chain-of-thought, extended thinking), as reported by the provider for this inference operation. [33] | `50` |
| [`gen_ai.usage.text.cache_read.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of text input tokens served from a provider-managed cache, as reported by the provider for this inference operation. [34] | `40` |
| [`gen_ai.usage.text.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of text input tokens, as reported by the provider for this inference operation. [35] | `100` |
| [`gen_ai.usage.text.output_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` When available and non-zero. | int | The number of text output tokens, as reported by the provider for this inference operation. [36] | `180` |
| [`ollama.request.base_url`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The base URL of the Ollama API endpoint. [37] | `http://localhost:11434`; `https://ollama.example.com` |
| [`ollama.response.load_duration`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The time in nanoseconds the model took to load. [38] | `500000000` |
| [`ollama.response.total_duration`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The total time in nanoseconds the model took to generate the response. [39] | `1500000000` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [40] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |
| [`gen_ai.input.messages`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | any | The chat history provided to the model as an input. [41] | [<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"role": "user",<br>&nbsp;&nbsp;&nbsp;&nbsp;"parts": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "text",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"content": "Weather in Paris?"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;},<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"role": "assistant",<br>&nbsp;&nbsp;&nbsp;&nbsp;"parts": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "tool_call",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"id": "call_VSPygqKTWdrhaFErNvMV18Yl",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"name": "get_weather",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"arguments": {<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"location": "Paris"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;},<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"role": "tool",<br>&nbsp;&nbsp;&nbsp;&nbsp;"parts": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "tool_call_response",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"id": "call_VSPygqKTWdrhaFErNvMV18Yl",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"response": "rainy, 57°F"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;}<br>] |
| [`gen_ai.input.messages_ref`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | string | An absolute URI identifying the input messages in external storage. [42] | `s3://example-bucket/gen-ai/674f35f4-e3f6-41f5-b104-864b3964f6d3_inputs.json` |
| [`gen_ai.output.messages`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | any | Messages returned by the model where each message represents a specific model response (choice, candidate). [43] | [<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"role": "assistant",<br>&nbsp;&nbsp;&nbsp;&nbsp;"parts": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "text",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"content": "The weather in Paris is currently rainy with a temperature of 57°F."<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;}<br>] |
| [`gen_ai.output.messages_ref`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | string | An absolute URI identifying the output messages in external storage. [44] | `s3://example-bucket/gen-ai/674f35f4-e3f6-41f5-b104-864b3964f6d3_outputs.json` |
| [`gen_ai.prompt.variable`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | string | The variables supplied to the prompt template, the `<key>` being the variable name, the value being the variable value. [45] | `Alice`; `French` |
| [`gen_ai.system_instructions`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | any | The system message or instructions provided to the GenAI model separately from the chat history. [46] | [<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"type": "text",<br>&nbsp;&nbsp;&nbsp;&nbsp;"content": "You are an Agent that greet users, always use greetings tool to respond"<br>&nbsp;&nbsp;}<br>]; [<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"type": "text",<br>&nbsp;&nbsp;&nbsp;&nbsp;"content": "You are a language translator."<br>&nbsp;&nbsp;},<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"type": "text",<br>&nbsp;&nbsp;&nbsp;&nbsp;"content": "Your mission is to translate text in English to French."<br>&nbsp;&nbsp;}<br>] |
| [`gen_ai.system_instructions_ref`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | string | An absolute URI identifying the system instructions in external storage. [47] | `s3://example-bucket/gen-ai/e68562472088cf0fec6124d5268608b01b1e248afb408e748738d39c6352d169_system_instruction.json` |
| [`gen_ai.tool.definitions`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | any | The list of tool definitions available to the GenAI agent or model. [48] | [<br>&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;"type": "function",<br>&nbsp;&nbsp;&nbsp;&nbsp;"name": "get_current_weather",<br>&nbsp;&nbsp;&nbsp;&nbsp;"description": "Get the current weather in a given location",<br>&nbsp;&nbsp;&nbsp;&nbsp;"parameters": {<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "object",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"properties": {<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"description": "The city and state, e.g. San Francisco, CA"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;},<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"unit": {<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"enum": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"celsius",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"fahrenheit"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;},<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"required": [<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"location",<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"unit"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;]<br>&nbsp;&nbsp;&nbsp;&nbsp;}<br>&nbsp;&nbsp;}<br>] |
| [`gen_ai.tool.definitions_ref`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Opt-In` | string | An absolute URI identifying the tool definitions in external storage. [49] | `s3://example-bucket/gen-ai/b61c3b21581c79d687c07f31970d1a9482dca47756ccf014d408fd6cd091ef66_tool.definitions.json` |

**[1] `gen_ai.operation.name`:** If one of the predefined values applies, but specific system uses a different name it's RECOMMENDED to document it in the semantic conventions for specific GenAI system and use system-specific name in the instrumentation. If a different name is not documented, instrumentation libraries SHOULD use applicable predefined value.

**[2] `error.type`:** The `error.type` SHOULD match the error code returned by the Generative AI provider or the client library,
the canonical name of exception that occurred, or another low-cardinality error identifier.
Instrumentations SHOULD document the list of errors they report.

**[3] `gen_ai.conversation.id`:** If and only if the instrumented library has one readily available, or the user application provides one through OpenTelemetry context or library-specific mechanisms.

**[4] `gen_ai.conversation.id`:** Instrumentations SHOULD populate conversation id when they have an identifier
for the conversation readily available for a given operation, for example:

- when the client framework being instrumented manages conversation history
(see [LlamaIndex chat store](https://docs.llamaindex.ai/en/stable/module_guides/storing/chat_stores/),
[LangChain `session_id`](https://reference.langchain.com/python/langchain-core/runnables/history/RunnableWithMessageHistory),
and [Google ADK sessions](https://adk.dev/sessions/session))
- when instrumenting GenAI client libraries that maintain a conversation on the backend
(see [AWS Bedrock agent sessions](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html),
[OpenAI Assistant threads](https://platform.openai.com/docs/api-reference/threads))

When no identifier for the conversation is available, instrumentations SHOULD NOT
populate conversation id. For example, a new UUID, a trace identifier, or a hash
of request content SHOULD NOT be used as a fallback value.

Application developers that manage conversation history MAY add conversation id to GenAI and other
spans or logs using custom span or log record processors or hooks provided by instrumentation
libraries.

**[5] `gen_ai.output.type`:** When applicable and if the request includes an output format.

**[6] `gen_ai.output.type`:** This attribute SHOULD be used when the client requests output of a specific type. The model may return zero or more outputs of this type.
This attribute specifies the output modality and not the actual output format. For example, if an image is requested, the actual output could be a URL pointing to an image file.
Additional output format details may be recorded in the future in the `gen_ai.output.{type}.*` attributes.

**[7] `gen_ai.prompt.version`:** when `gen_ai.prompt.name` is set and a version is available

**[8] `gen_ai.prompt.version`:** The version string can follow any versioning scheme chosen by the
application (e.g., SemVer, date-based, or platform-specific tags).
When a prompt management system is in use, this SHOULD match the
version identifier used by that system.

**[9] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[10] `gen_ai.request.stream`:** If and only if the request is streaming. If unset, the request is assumed to be non-streaming.

**[11] `gen_ai.request.top_k`:** This is a decoding/sampling parameter (e.g., Anthropic `top_k`, Cohere `k`, Google `topK`), not an output-shaping parameter. In particular, OpenAI's `top_logprobs` controls how many per-token log-probabilities are returned in the response and does not change generation; it MUST NOT be reported as `gen_ai.request.top_k`.

**[12] `ollama.request.main_gpu`:** Corresponds to the `main_gpu` option in the request `options` object.

**[13] `ollama.request.num_batch`:** Corresponds to the `num_batch` option in the request `options` object.

**[14] `ollama.request.num_ctx`:** Corresponds to the `num_ctx` option in the request `options` object.

**[15] `ollama.request.num_gpu`:** Corresponds to the `num_gpu` option in the request `options` object.

**[16] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[17] `gen_ai.conversation.compacted`:** This attribute is a positive indicator of context compaction. Instrumentations
SHOULD set it to `true` only when they can reliably determine that context
compaction was applied. Instrumentations SHOULD NOT set it to `false`; they
SHOULD leave it unset otherwise.

**[18] `gen_ai.request.previous_response.id`:** When available and if the request references a previous response.

**[19] `gen_ai.request.previous_response.id`:** Instrumentations SHOULD populate this attribute when the request references a previous response or interaction identifier to continue a conversation or pass prior context.
For example, `previous_response_id` in [OpenAI Responses API](https://developers.openai.com/api/docs/guides/conversation-state#passing-context-from-the-previous-response)
or `previous_interaction_id` in [Google GenAI Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview).

**[20] `gen_ai.request.reasoning.level`:** The value SHOULD be the exact string value sent to the provider.
Semantic conventions for individual providers SHOULD document which input parameter maps to this attribute.

**[21] `gen_ai.response.finish_reasons`:** Values correspond to generations in the same order as the returned
choices/candidates.

For interrupted generations, instrumentations SHOULD report the
provider-reported interruption reason when available and `interrupted` otherwise.

Each position SHOULD contain the finish reason for the corresponding
choice/candidate. If a finish reason was expected but not received, for
example because generation failed, was cancelled, or a stream ended before
the final event, instrumentations SHOULD report `error` for that position
instead of omitting it.

`error` indicates that the generation ended abnormally, whether reported
by the provider or inferred by the instrumentation.

**[22] `gen_ai.response.time_to_first_chunk`:** A chunk is a decoded provider stream event carrying new, non-empty output: text, refusals, reasoning (including opaque payloads), audio, images, or tool-call names or arguments. Instrumentations MUST NOT treat empty start events or events carrying only usage, roles, IDs, signatures, keep-alives, progress/status updates, or end markers as chunks. Chunk boundaries follow provider events, not TCP reads, HTTP frames, or extra SDK callbacks.

Instrumentations SHOULD measure the time from the start of the logical inference operation, before authentication and the first attempt, to when the first chunk is fully received by the client, before application processing. The measurement SHOULD include authentication, failed attempts, and retry backoff.

Instrumentations SHOULD set this attribute when the first chunk is received and MUST NOT set it if no chunk is received.

**[23] `gen_ai.usage.audio.cache_read.input_tokens`:** The value SHOULD be included in `gen_ai.usage.cache_read.input_tokens` and in `gen_ai.usage.audio.input_tokens`.

**[24] `gen_ai.usage.audio.input_tokens`:** The value SHOULD be included in `gen_ai.usage.input_tokens`.

**[25] `gen_ai.usage.audio.output_tokens`:** The value SHOULD be included in `gen_ai.usage.output_tokens`.

**[26] `gen_ai.usage.cache_read.input_tokens`:** The value SHOULD be included in `gen_ai.usage.input_tokens`.

**[27] `gen_ai.usage.cache_write.input_tokens`:** The value SHOULD be included in `gen_ai.usage.input_tokens`.

**[28] `gen_ai.usage.image.cache_read.input_tokens`:** The value SHOULD be included in `gen_ai.usage.cache_read.input_tokens` and in `gen_ai.usage.image.input_tokens`.

**[29] `gen_ai.usage.image.input_tokens`:** The value SHOULD be included in `gen_ai.usage.input_tokens`.

**[30] `gen_ai.usage.image.output_tokens`:** The value SHOULD be included in `gen_ai.usage.output_tokens`.

**[31] `gen_ai.usage.input_tokens`:** This value SHOULD include cached tokens and input tokens of all modalities.
Instrumentations SHOULD make a best effort to populate this value, using a total
provided by the provider when available or, depending on the provider API,
by summing different token types parsed from the provider output.

When the provider reports both billed token counts and model-consumed
token counts (for example, Cohere exposes both `usage.billed_units` and
`usage.tokens`), instrumentations SHOULD report the billed count so the
value matches the units the customer is charged for.

Detailed usage attributes are subsets of total and aggregate counts. For example,
if a request has 100 text tokens (40 cached) and 200 image tokens:
- `gen_ai.usage.input_tokens`: 300
- `gen_ai.usage.cache_read.input_tokens`: 40
- `gen_ai.usage.text.input_tokens`: 100
- `gen_ai.usage.text.cache_read.input_tokens`: 40
- `gen_ai.usage.image.input_tokens`: 200

**[32] `gen_ai.usage.output_tokens`:** This value SHOULD include reasoning tokens and tokens of all modalities.

When the provider reports both billed token counts and model-consumed
token counts (for example, Cohere exposes both `usage.billed_units` and
`usage.tokens`), instrumentations SHOULD report the billed count so the
value matches the units the customer is charged for.

**[33] `gen_ai.usage.reasoning.output_tokens`:** The value SHOULD be included in `gen_ai.usage.output_tokens`.

**[34] `gen_ai.usage.text.cache_read.input_tokens`:** The value SHOULD be included in `gen_ai.usage.cache_read.input_tokens` and in `gen_ai.usage.text.input_tokens`.

**[35] `gen_ai.usage.text.input_tokens`:** The value SHOULD be included in `gen_ai.usage.input_tokens`.

**[36] `gen_ai.usage.text.output_tokens`:** The value SHOULD be included in `gen_ai.usage.output_tokens`.

**[37] `ollama.request.base_url`:** Corresponds to the `host` configuration of the Ollama client: the base URL of the API endpoint the client connects to. User information (credentials) embedded in the URL MUST be removed before the URL is recorded, and sensitive query parameter values MUST be scrubbed.

**[38] `ollama.response.load_duration`:** Corresponds to the `load_duration` field of the Ollama response.

**[39] `ollama.response.total_duration`:** Corresponds to the `total_duration` field of the Ollama response.

**[40] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

**[41] `gen_ai.input.messages`:** Messages MUST be provided in the order they were sent to the model.
Instrumentations MAY provide a way for users to filter or truncate
input messages.

> [!Warning]
> This attribute is likely to contain sensitive information including user/PII data.

See [Recording content on attributes](/docs/gen-ai/gen-ai-spans.md#recording-content-on-attributes)
section for more details.

This attribute MUST be recorded as an [AnyValue](https://opentelemetry.io/docs/specs/otel/common/#anyvalue) conforming to its [JSON schema](/model/gen-ai/gen-ai-input-messages.json).

**[42] `gen_ai.input.messages_ref`:** The presence of this attribute does not indicate whether storing the
content succeeded or whether the content remains available.

It is NOT RECOMMENDED to embed credentials, such as signed URL
query parameters, in the URI. Access to the stored content SHOULD be
secured by other means, for example by storage-level access control.

> [!Warning]
> The URI may expose sensitive storage metadata, such as storage provider,
> bucket or container names, tenant or object identifiers.

**[43] `gen_ai.output.messages`:** Each message represents a single output choice/candidate generated by
the model. Each message corresponds to exactly one generation
(choice/candidate) and vice versa - one choice cannot be split across
multiple messages or one message cannot contain parts from multiple choices.

Instrumentations MAY provide a way for users to filter or truncate
output messages. `gen_ai.response.finish_reasons` remains aligned with the
generations returned by the provider, not with a filtered or truncated
`gen_ai.output.messages` value.

When an operation ends in an error, this attribute SHOULD only be set
when the operation produced output, including partial streamed output.
Instrumentation SHOULD NOT synthesize output content for a failed
operation.

> [!Warning]
> This attribute is likely to contain sensitive information including user/PII data.

See [Recording content on attributes](/docs/gen-ai/gen-ai-spans.md#recording-content-on-attributes)
section for more details.

This attribute MUST be recorded as an [AnyValue](https://opentelemetry.io/docs/specs/otel/common/#anyvalue) conforming to its [JSON schema](/model/gen-ai/gen-ai-output-messages.json).

**[44] `gen_ai.output.messages_ref`:** The presence of this attribute does not indicate whether storing the
content succeeded or whether the content remains available.

It is NOT RECOMMENDED to embed credentials, such as signed URL
query parameters, in the URI. Access to the stored content SHOULD be
secured by other means, for example by storage-level access control.

> [!Warning]
> The URI may expose sensitive storage metadata, such as storage provider,
> bucket or container names, tenant or object identifiers.

**[45] `gen_ai.prompt.variable`:** Prompt templates are parameterized with variables that are filled in
at runtime. This attribute records the variable values passed to the
template. The attribute name defines the variable name, and the
attribute value is the variable value serialized as a string.

Examples:

- A variable `user_name` with value `Alice` SHOULD be recorded as
  the `gen_ai.prompt.variable.user_name` attribute with value `"Alice"`.
- A variable `language` with value `French` SHOULD be recorded as
  the `gen_ai.prompt.variable.language` attribute with value `"French"`.

> [!Warning]
> This attribute may contain sensitive information.

**[46] `gen_ai.system_instructions`:** This attribute SHOULD be used when the corresponding provider or API
allows to provide system instructions or messages separately from the
chat history.

Instructions that are part of the chat history SHOULD be recorded in
`gen_ai.input.messages` attribute instead.

Instrumentations MAY provide a way for users to filter or truncate
system instructions.

> [!Warning]
> This attribute may contain sensitive information.

See [Recording content on attributes](/docs/gen-ai/gen-ai-spans.md#recording-content-on-attributes)
section for more details.

This attribute MUST be recorded as an [AnyValue](https://opentelemetry.io/docs/specs/otel/common/#anyvalue) conforming to its [JSON schema](/model/gen-ai/gen-ai-system-instructions.json).

**[47] `gen_ai.system_instructions_ref`:** The presence of this attribute does not indicate whether storing the
content succeeded or whether the content remains available.

It is NOT RECOMMENDED to embed credentials, such as signed URL
query parameters, in the URI. Access to the stored content SHOULD be
secured by other means, for example by storage-level access control.

> [!Warning]
> The URI may expose sensitive storage metadata, such as storage provider,
> bucket or container names, tenant or object identifiers.

**[48] `gen_ai.tool.definitions`:**

> [!WARNING]
> This attribute may contain sensitive information.

Since this attribute could be large, it's NOT RECOMMENDED to populate
non-required properties by default. Instrumentations MAY provide a way
to enable populating optional properties.

This attribute MUST be recorded as an [AnyValue](https://opentelemetry.io/docs/specs/otel/common/#anyvalue) conforming to its [JSON schema](/model/gen-ai/gen-ai-tool-definitions.json).

**[49] `gen_ai.tool.definitions_ref`:** The presence of this attribute does not indicate whether storing the
content succeeded or whether the content remains available.

It is NOT RECOMMENDED to embed credentials, such as signed URL
query parameters, in the URI. Access to the stored content SHOULD be
secured by other means, for example by storage-level access control.

> [!Warning]
> The URI may expose sensitive storage metadata, such as storage provider,
> bucket or container names, tenant or object identifiers.

The following attributes can be important for making sampling decisions
and SHOULD be provided **at span creation time** (if provided at all):

* [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md)
* [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md)
* [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md)
* [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md)

---

`error.type` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `_OTHER` | A fallback error value to be used when the instrumentation doesn't define a custom value. | ![Stable](https://img.shields.io/badge/-stable-lightgreen) |

---

`gen_ai.operation.name` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `chat` | Chat completion operation such as [OpenAI Chat API](https://platform.openai.com/docs/api-reference/chat) | ![Development](https://img.shields.io/badge/-development-blue) |
| `create_agent` | Create GenAI agent | ![Development](https://img.shields.io/badge/-development-blue) |
| `create_memory` | Create new memory records | ![Development](https://img.shields.io/badge/-development-blue) |
| `create_memory_store` | Create or initialize a memory store | ![Development](https://img.shields.io/badge/-development-blue) |
| `delete_memory` | Delete memory records | ![Development](https://img.shields.io/badge/-development-blue) |
| `delete_memory_store` | Delete or deprovision a memory store | ![Development](https://img.shields.io/badge/-development-blue) |
| `embeddings` | Embeddings operation such as [OpenAI Create embeddings API](https://platform.openai.com/docs/api-reference/embeddings/create) | ![Development](https://img.shields.io/badge/-development-blue) |
| `execute_tool` | Execute a tool | ![Development](https://img.shields.io/badge/-development-blue) |
| `fetch_response` | Fetch a previously generated model response by its identifier, without performing inference, such as [OpenAI Get a model response](https://platform.openai.com/docs/api-reference/responses/get) [50] | ![Development](https://img.shields.io/badge/-development-blue) |
| `generate_content` | Multimodal content generation operation such as [Gemini Generate Content](https://ai.google.dev/api/generate-content) | ![Development](https://img.shields.io/badge/-development-blue) |
| `invoke_agent` | Invoke GenAI agent | ![Development](https://img.shields.io/badge/-development-blue) |
| `invoke_runner` | Invoke a framework runner that is not itself an agent or a workflow | ![Development](https://img.shields.io/badge/-development-blue) |
| `invoke_workflow` | Invoke GenAI workflow | ![Development](https://img.shields.io/badge/-development-blue) |
| `plan` | Agent planning or task decomposition phase | ![Development](https://img.shields.io/badge/-development-blue) |
| `realtime_inference` | Server-side model generation within a realtime, bidirectional streaming session such as [OpenAI Realtime](https://platform.openai.com/docs/guides/realtime) or [Gemini Live](https://ai.google.dev/gemini-api/docs/live). | ![Development](https://img.shields.io/badge/-development-blue) |
| `retrieval` | Execution of a retrieval pipeline that returns documents relevant to a query [51] | ![Development](https://img.shields.io/badge/-development-blue) |
| `search_memory` | Search/query memories from a memory store | ![Development](https://img.shields.io/badge/-development-blue) |
| `text_completion` | Text completions operation such as [OpenAI Completions API (Legacy)](https://platform.openai.com/docs/api-reference/completions) | ![Development](https://img.shields.io/badge/-development-blue) |
| `update_memory` | Update existing memory records | ![Development](https://img.shields.io/badge/-development-blue) |
| `upsert_memory` | Create or update memory records without the caller choosing which | ![Development](https://img.shields.io/badge/-development-blue) |
| `user_speech` | Describes the process of recording user speech input. | ![Development](https://img.shields.io/badge/-development-blue) |

**[50]:** Instrumentations SHOULD NOT report token usage (as attributes or metrics) for this operation.

**[51]:** Examples include LangChain, LlamaIndex, and Haystack retrievers.
A retrieval pipeline usually combines other operations such as embeddings,
database queries, web search, or reranking. These operations SHOULD be
reported following their own conventions.

---

`gen_ai.output.type` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `image` | Image | ![Development](https://img.shields.io/badge/-development-blue) |
| `json` | JSON object with known or unknown schema | ![Development](https://img.shields.io/badge/-development-blue) |
| `speech` | Speech | ![Development](https://img.shields.io/badge/-development-blue) |
| `text` | Plain text | ![Development](https://img.shields.io/badge/-development-blue) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
<!-- endweaver -->

### Embeddings

`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

<!-- weaver .refinements.spans[] | select(.id == "ollama.gen_ai.client.embeddings") | .attributes |= map(select(.key != "gen_ai.provider.name")) -->
<!-- NOTE: THIS TEXT IS AUTOGENERATED. DO NOT EDIT BY HAND. -->
<!-- see templates/registry/markdown/snippet.md.j2 -->
<!-- prettier-ignore-start -->

**Status:** ![Development](https://img.shields.io/badge/-development-blue)

Semantic Conventions for [Ollama](https://ollama.com/) embeddings operations extend and override the semantic conventions for [Gen AI Spans](gen-ai-spans.md).

`gen_ai.provider.name` MUST be set to `"ollama"` and SHOULD be provided **at span creation time**.

**Span name** SHOULD be `{gen_ai.operation.name} {gen_ai.request.model}`.

**Span kind** SHOULD be `CLIENT`.

**Span status** SHOULD follow the [Recording Errors](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/recording-errors.md) document.

**Requirement level:** [Recommended](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/general/signal-requirement-level.md).

**Attributes:**

| Key | Stability | [Requirement Level](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) | Value Type | Description | Example Values |
| --- | --- | --- | --- | --- | --- |
| [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Required` | string | The name of the operation being performed. [1] | `embeddings` |
| [`error.type`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/error.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If the operation ended in an error. | string | Describes a class of error the operation ended with. [2] | `timeout`; `java.net.UnknownHostException`; `server_certificate_invalid`; `500` |
| [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If available. | string | The name of the GenAI model a request is being made to. [3] | `text-embedding-3-small`; `gemini-embedding-001` |
| [`ollama.request.main_gpu`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `main_gpu`. | int | The index of the main GPU to use. [4] | `0`; `1` |
| [`ollama.request.num_batch`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_batch`. | int | The number of tokens to process in parallel. [5] | `8`; `16`; `32` |
| [`ollama.request.num_ctx`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_ctx`. | int | The size of the context window for the model. [6] | `2048`; `4096`; `32768` |
| [`ollama.request.num_gpu`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Conditionally Required` If the request `options` include `num_gpu`. | int | The number of model layers to offload to GPUs for inference. [7] | `1`; `2`; `4` |
| [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Conditionally Required` If `server.address` is set. | int | GenAI server port. [8] | `80`; `8080`; `443` |
| [`gen_ai.embeddings.dimension.count`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The number of dimensions the resulting output embeddings should have. | `512`; `1024` |
| [`gen_ai.request.encoding_formats`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string[] | The encoding formats requested in an embeddings operation, if specified. [9] | `["base64"]`; `["float", "binary"]` |
| [`gen_ai.response.model`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The name of the model that generated the response. | `text-embedding-3-small` |
| [`gen_ai.usage.input_tokens`](/docs/registry/attributes/gen-ai.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The total number of input (prompt) tokens across all modalities. [10] | `100` |
| [`ollama.request.base_url`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | string | The base URL of the Ollama API endpoint. [11] | `http://localhost:11434`; `https://ollama.example.com` |
| [`ollama.response.load_duration`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The time in nanoseconds the model took to load. [12] | `500000000` |
| [`ollama.response.total_duration`](/docs/registry/attributes/ollama.md) | ![Development](https://img.shields.io/badge/-development-blue) | `Recommended` | int | The total time in nanoseconds the model took to generate the response. [13] | `1500000000` |
| [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md) | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | `Recommended` | string | GenAI server address. [14] | `example.com`; `10.1.2.80`; `/tmp/my.sock` |

**[1] `gen_ai.operation.name`:** SHOULD be `embeddings`.

**[2] `error.type`:** The `error.type` SHOULD match the error code returned by the Generative AI provider or the client library,
the canonical name of exception that occurred, or another low-cardinality error identifier.
Instrumentations SHOULD document the list of errors they report.

**[3] `gen_ai.request.model`:** The name of the GenAI model a request is being made to. If the model is supplied by a vendor, then the value must be the exact name of the model requested. If the model is a fine-tuned custom model, the value should have a more specific name than the base model that's been fine-tuned.

**[4] `ollama.request.main_gpu`:** Corresponds to the `main_gpu` option in the request `options` object.

**[5] `ollama.request.num_batch`:** Corresponds to the `num_batch` option in the request `options` object.

**[6] `ollama.request.num_ctx`:** Corresponds to the `num_ctx` option in the request `options` object.

**[7] `ollama.request.num_gpu`:** Corresponds to the `num_gpu` option in the request `options` object.

**[8] `server.port`:** When observed from the client side, and when communicating through an intermediary, `server.port` SHOULD represent the server port behind any intermediaries, for example proxies, if it's available.

**[9] `gen_ai.request.encoding_formats`:** In some GenAI systems the encoding formats are called embedding types. Also, some GenAI systems only accept a single format per request.

**[10] `gen_ai.usage.input_tokens`:** The total number of input tokens across all inputs in the request,
as reported by the provider.

When the provider reports both billed and model-consumed token counts,
instrumentations SHOULD report the billed count.

**[11] `ollama.request.base_url`:** Corresponds to the `host` configuration of the Ollama client: the base URL of the API endpoint the client connects to. User information (credentials) embedded in the URL MUST be removed before the URL is recorded, and sensitive query parameter values MUST be scrubbed.

**[12] `ollama.response.load_duration`:** Corresponds to the `load_duration` field of the Ollama response.

**[13] `ollama.response.total_duration`:** Corresponds to the `total_duration` field of the Ollama response.

**[14] `server.address`:** When observed from the client side, and when communicating through an intermediary, `server.address` SHOULD represent the server address behind any intermediaries, for example proxies, if it's available.

The following attributes can be important for making sampling decisions
and SHOULD be provided **at span creation time** (if provided at all):

* [`gen_ai.operation.name`](/docs/registry/attributes/gen-ai.md)
* [`gen_ai.request.model`](/docs/registry/attributes/gen-ai.md)
* [`server.address`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md)
* [`server.port`](https://github.com/open-telemetry/semantic-conventions/blob/v1.45.0/docs/registry/attributes/server.md)

---

`error.type` has the following list of well-known values. If one of them applies, then the respective value MUST be used; otherwise, a custom value MAY be used.

| Value | Description | Stability |
| --- | --- | --- |
| `_OTHER` | A fallback error value to be used when the instrumentation doesn't define a custom value. | ![Stable](https://img.shields.io/badge/-stable-lightgreen) |

<!-- prettier-ignore-end -->
<!-- END AUTOGENERATED TEXT -->
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

