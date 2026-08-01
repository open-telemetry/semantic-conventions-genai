# google-genai

The `google-genai` client is a **model-call boundary**: it calls the Gemini API
directly, so it owns inference and embeddings. It also supports **automatic
function calling** — when tools are Python callables, the SDK executes them — so
tool execution is instrumentable here.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | Yes — automatic function calling executes the tool | ✅ Implemented | 
