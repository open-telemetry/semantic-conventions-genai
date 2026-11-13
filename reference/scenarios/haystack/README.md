# haystack

Haystack runs pipelines of components. It calls models through generator
components, so it **delegates inference** to the underlying LLM library. It owns
the retrieval and pipeline (workflow) operations it runs directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model provider (e.g. `openai`) | ✅ Correctly not emitted |
| retrieval | Yes — retriever component | ✅ Implemented |
| invoke_workflow | Yes — pipeline (graph) execution | ❌ Not implemented |

The retrieval scenario records each returned document's content, metadata, ID, and BM25 score.
Haystack supplies content-derived IDs when none are provided; unavailable fields are omitted.
