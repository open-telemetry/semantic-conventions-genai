# Ollama reference scenario

The `ollama` client is a **model-call boundary**: it calls the Ollama server directly,
so it owns inference and embeddings. Tool calling is supported by the API, with the
tool itself running in application code.

Demonstrates the [Ollama technology-specific semantic conventions](../../../docs/gen-ai/ollama.md)
on the standard GenAI client spans, using the `ollama` SDK against the mock
Ollama server. The scenarios cover a basic chat completion, a chat completion
that offers a tool and receives a tool call, a formatted chat completion requesting
JSON output, a streaming chat completion, a streaming tool call served by a
scenario-local `/api/chat` mock, a cached prompt-token chat served by a scenario-local
`/api/chat` mock with a raw-response capture workaround, a streaming chat completion
that fails mid-stream when a scenario-local mock drops the connection, chat
completions exercising the
`SPAN_ONLY` and `SPAN_AND_EVENT` content capture modes on the span, an embedding
generation, a text completion against a scenario-local `/api/generate` mock, and
the failure paths of chat and embeddings.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| inference (`text_completion`) | Yes — `client.generate` calls the model directly | ✅ Implemented (against a scenario-local `/api/generate` mock; the shared mock server implements `/api/chat` and `/api/embed` only) |
| embeddings | Yes — `client.embed` calls the model directly | ✅ Implemented |
| execute_tool | No — the client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |

## Signals emitted

- `gen_ai.client.inference` span for a chat completion (`gen_ai.operation.name = "chat"`), including:
  - generic GenAI request, response, and usage attributes
  - `gen_ai.tool.definitions` when the request offers tools — recorded only when
    tool-definition capture is opted in via `OTEL_INSTRUMENTATION_GENAI_CAPTURE_TOOL_DEFINITIONS`,
    since tool schemas may be large and may contain sensitive information — and
    `tool_call` message parts when the model answers with a tool call, keeping any
    text of the same response as an independent part
  - `gen_ai.input.messages` and `gen_ai.output.messages` when message-content
    capture is opted in with the `SPAN_ONLY` or `SPAN_AND_EVENT` mode of
    `OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT`, per the content capture
    configuration of the generic conventions
  - `gen_ai.output.type = "json"` when the request passes `format = "json"`
  - `gen_ai.request.stream` and `gen_ai.response.time_to_first_chunk` for streaming requests
  - `ollama.request.base_url` and the `num_ctx`, `num_batch`, `num_gpu`, and
    `main_gpu` Ollama-specific request options, each read from the same
    `options` object handed to the SDK call
  - `ollama.response.total_duration` and `ollama.response.load_duration` from the native Ollama response timings
  - `gen_ai.usage.cache_read.input_tokens` for the cached prompt-token chat: the
    scenario-local mock reports a non-zero `prompt_eval_cached_count` that
    `ollama-python` drops when parsing, so a capture transport injected into the
    SDK's httpx client through the supported `transport` argument reads the field
    from the raw response — a workaround that is removed once an SDK release
    exposes the field
- `gen_ai.client.inference` span for a text completion
  (`gen_ai.operation.name = "text_completion"`) from the `client.generate` call,
  served by a scenario-local `/api/generate` HTTP mock because the shared
  conformance mock server does not implement the endpoint
- `gen_ai.client.embeddings` span for an embedding generation
  (`gen_ai.operation.name = "embeddings"`) with the embedding dimension count, the
  input token usage, the native Ollama response timings, and the `num_ctx`,
  `num_batch`, `num_gpu`, and `main_gpu` request options passed through the SDK
  `options` object
- `gen_ai.client.inference.operation.details` event (DEBUG severity) with the input
  and output messages — the event carries them when the `EVENT_ONLY` or
  `SPAN_AND_EVENT` capture mode is enabled via `OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT`,
  while the span carries them when the `SPAN_ONLY` or `SPAN_AND_EVENT` mode is
  enabled — the server endpoint, the request options, the usage counts including
  the captured cached prompt tokens, and `gen_ai.response.time_to_first_chunk` for
  the streaming requests
- `gen_ai.client.inference.exception` and `gen_ai.client.embeddings.exception` events
  (WARN severity) on the SDK failure paths
- `gen_ai.client.inference.duration` around the SDK chat and generate calls, with the
  explicit bucket boundaries recommended by the GenAI conventions
- `gen_ai.client.inference.usage.input_tokens` and `gen_ai.client.inference.usage.output_tokens`
  counters, recorded under the `unknown` modality because Ollama reports no per-modality
  token breakdown, plus the `gen_ai.client.inference.usage.cache_read.input_tokens` counter
  for the cached prompt-token chat, a subset of the input-token usage counter
- `gen_ai.client.inference.operation.input_tokens` and `gen_ai.client.inference.operation.output_tokens` histograms
- `gen_ai.client.inference.time_to_first_chunk` and `gen_ai.client.inference.time_per_output_chunk` histograms
  for the streaming chat completions, recorded from the arrival times of the chunks
  that carry new output — text, reasoning, or tool-call names or arguments, per the
  chunk definition of the generic attribute — and still recorded on a failed stream
  when a chunk arrived
- `gen_ai.client.embeddings.duration` and `gen_ai.client.embeddings.operation.input_tokens`

Ollama's `num_predict` option is recorded as `gen_ai.request.max_tokens` only for
non-negative values (negative values are Ollama sentinels, for example `-1` for
unlimited generation), and the native `prompt_eval_count` and `eval_count` response
fields as `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`.

The cached prompt-token chat additionally records the server's
`prompt_eval_cached_count` as `gen_ai.usage.cache_read.input_tokens`, a subset of
`gen_ai.usage.input_tokens`, and counts it on the
`gen_ai.client.inference.usage.cache_read.input_tokens` counter, a subset
of the input-token usage counter. Because `ollama-python` drops the field when parsing
the response, the scenario reads it from the raw response through a capture
transport injected into the SDK's httpx client — a workaround that is removed once
an SDK release exposes the field; streamed responses are skipped so the
time-to-first-chunk timing is preserved.

When a response omits an expected finish reason, for example a stream that ends
without a final chunk, the fallback required by the generic conventions records
`gen_ai.response.finish_reasons = ["error"]`.

The failure paths point the SDK at a server that accepts no connections, or at a
scenario-local mock that drops the connection mid-stream: they record
`error.type` and `gen_ai.response.finish_reasons = ["error"]` on the failed chat span,
the duration and zero-valued token histograms on the metrics, emit the GenAI exception
events, and re-raise the SDK exception. A failed streaming chat preserves
`gen_ai.response.time_to_first_chunk` on the span and still records the streaming chunk
histograms when a chunk arrived before the failure. The mid-stream failure runs with the
`SPAN_AND_EVENT` capture mode, so its partial output is recorded on the span and, since
the exception event may only copy attributes captured on the span, also carried by the
exception event. The run fails if a failure-path call does not raise.

## Conformance

`conformance.yaml` declares value assertions for every chat, text completion, and
embeddings span, including the failure spans, and enables message-content capture
(`OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT=EVENT_ONLY`) so the operation details
events carry the input and output messages, and tool-definition capture
(`OTEL_INSTRUMENTATION_GENAI_CAPTURE_TOOL_DEFINITIONS=true`) so the offered tool
definitions are recorded. The span content capture modes are exercised with per-call
overrides, so the runs with `SPAN_ONLY` and `SPAN_AND_EVENT` record the input and
output messages on the span.
The cached prompt-token chat asserts the cached, total input, and output
token counts of its span.

## Running

From the `reference/` directory:

```bash
uv run run-scenario ollama
```

## References

- [Ollama technology-specific semantic conventions](../../../docs/gen-ai/ollama.md)
- [Ollama documentation](https://docs.ollama.com/)

