Add `gen_ai.client.embeddings.duration` and `gen_ai.client.embeddings.operation.input_tokens` metrics, consolidate embeddings client span and metrics in `client-embeddings.md`.

Embeddings operations are no longer reported on `gen_ai.client.operation.duration` - use `gen_ai.client.embeddings.duration` instead. Embeddings token usage previously reported on `gen_ai.client.token.usage` is now reported on `gen_ai.client.embeddings.operation.input_tokens`.
