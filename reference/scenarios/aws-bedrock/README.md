# aws-bedrock

The Bedrock Runtime client (`Converse` / `InvokeModel`) is a **model-call
boundary**: it calls the model directly, so it owns inference and embeddings.
Converse tool use is supported, with the tool itself running in application
code. (Knowledge Bases / Agents live in separate Bedrock services and scenarios.)

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — `Converse` / `InvokeModel`, calls the model directly | ✅ Implemented |
| embeddings | Yes — Titan / Cohere embedding models via `InvokeModel` | ✅ Implemented |
| execute_tool | No — Converse returns tool-use requests but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |
