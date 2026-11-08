# Ollama reference scenario

The `ollama` client is a **model-call boundary**: it calls the Ollama server directly,
so it owns inference and embeddings. Tool calling is supported by the API, with the
tool itself running in application code.

Demonstrates the [Ollama technology-specific semantic conventions](../../../docs/gen-ai/ollama.md)
on the standard GenAI client spans, using the `ollama` SDK against the mock
Ollama server.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| inference (`text_completion`) | Yes — `client.generate` calls the model directly | ❌ Not implemented (the mock server does not implement `/api/generate`) |
| embeddings | Yes — `client.embed` calls the model directly | ✅ Implemented |

## Signals emitted

- `gen_ai.client.inference` span for a chat completion (`gen_ai.operation.name = "chat"`), including:
  - generic GenAI request, response, and usage attributes
  - `ollama.request.base_url` and the `num_ctx`, `num_batch`, `num_gpu`, `main_gpu`,
    `low_vram`, and `f16_kv` Ollama-specific request options, each read from the same
    `options` object handed to the SDK call
  - `ollama.response.total_duration` and `ollama.response.load_duration` from the native Ollama response timings
- `gen_ai.client.embeddings` span for an embedding generation
  (`gen_ai.operation.name = "embeddings"`), with the embedding dimension count, the
  input token usage, and the native Ollama response timings
- `gen_ai.client.inference.operation.details` event with the input and output messages
- `gen_ai.client.inference.duration` around the SDK chat call
- `gen_ai.client.inference.usage.input_tokens` and `gen_ai.client.inference.usage.output_tokens`
  counters, recorded under the `unknown` modality because Ollama reports no per-modality
  token breakdown
- `gen_ai.client.inference.operation.input_tokens` and `gen_ai.client.inference.operation.output_tokens` histograms
- `gen_ai.client.embeddings.duration` and `gen_ai.client.embeddings.operation.input_tokens`

Ollama's `num_predict` option is recorded as `gen_ai.request.max_tokens`, and the
native `prompt_eval_count` and `eval_count` response fields as `gen_ai.usage.input_tokens`
and `gen_ai.usage.output_tokens`.

## Running

From the `reference/` directory:

```bash
uv run run-scenario ollama
```

## References

- [Ollama technology-specific semantic conventions](../../../docs/gen-ai/ollama.md)
- [Ollama documentation](https://docs.ollama.com/)
