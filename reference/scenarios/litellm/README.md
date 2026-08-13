# litellm

LiteLLM is a unified gateway that translates calls to many providers and makes
the model HTTP request itself, so it is a **model-call boundary**: it owns
inference and embeddings. Tool calling is supported, with the tool itself
running in application code.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the provider model directly | ✅ Implemented |
| embeddings | Yes — calls the provider model directly | ✅ Implemented |
| execute_tool | No — the client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
