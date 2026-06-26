# azure-openai

The Azure OpenAI client (the `openai` SDK pointed at an Azure endpoint) is a
**model-call boundary**: it calls the model directly, so it owns inference and
embeddings. Tool calling is supported, but the client returns tool calls
without executing them.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the client doesn't execute tools; the tool runs in app code | ➖ Not instrumentable |


