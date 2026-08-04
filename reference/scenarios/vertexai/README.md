# vertexai

> [!WARNING]
> **Deprecated.** The generative AI modules of the Vertex AI SDK
> (`vertexai.generative_models`, `vertexai.language_models`,
> `vertexai.vision_models`, `vertexai.caching`, `vertexai.tuning`) were
> deprecated by Google and are no longer available after June 24, 2026 — see the
> [Vertex AI SDK migration guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk).
> The successor is the Google Gen AI SDK (`google-genai`), covered by the
> [google-genai](../google-genai/) scenario.
>
> This scenario is kept only as existing evidence for already-proven
> conventions. No new operations will be added to it, and it will be removed
> from the reference in a future change.

The Vertex AI generative-models client is a **model-call boundary**: it calls
the model directly, so it owns inference. It supports **automatic function
calling** — when tools are Python callables, the SDK executes them — so tool
execution is instrumentable here.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| execute_tool | Yes — automatic function calling executes the tool (`preview` surface in google-cloud-aiplatform 2.x) | ✅ Implemented |
| embeddings | Yes — text-embeddings API | ➖ Won't add — SDK deprecated |
| create_agent | Yes — Agent Engine hosts agents remotely | ➖ Won't add — SDK deprecated |
| invoke_agent (client) | Yes — Agent Engine hosts agents remotely | ➖ Won't add — SDK deprecated |
