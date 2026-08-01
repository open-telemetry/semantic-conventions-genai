# vertexai

The Vertex AI generative-models client is a **model-call boundary**: it calls
the model directly, so it owns inference. Vertex AI also has a text-embeddings
API. It supports **automatic function calling** — when tools are Python
callables, the SDK executes them — so tool execution is instrumentable here.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — Vertex AI text-embeddings API | ❌ Not implemented |
| execute_tool | Yes — automatic function calling executes the tool | ❌ Not implemented |
