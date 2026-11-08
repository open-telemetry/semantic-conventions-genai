# Ollama reference scenario

Demonstrates the [Ollama technology-specific semantic conventions](../../../docs/gen-ai/ollama.md)
on the standard GenAI client inference span, using the `ollama` SDK against the mock
Ollama server.

## Signals emitted

- `gen_ai.client.inference` span for a chat completion (`gen_ai.operation.name = "chat"`), including:
  - generic GenAI request, response, and usage attributes
  - `ollama.request.base_url` and `ollama.request.num_ctx` for Ollama-specific request options
  - `ollama.response.total_duration` and `ollama.response.load_duration` from the native Ollama response timings
- `gen_ai.client.inference.operation.details` event with the input and output messages

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
