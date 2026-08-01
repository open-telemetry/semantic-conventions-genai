# cohere

The `cohere` client is a **model-call boundary**: it calls the model directly,
so it owns inference and embeddings. Tool calling is supported, with the tool
itself running in application code.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |

