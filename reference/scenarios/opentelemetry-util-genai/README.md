# opentelemetry-util-genai

`opentelemetry-util-genai` provides shared instrumentation utilities, including
an asynchronous completion hook that stores captured GenAI content externally.
This scenario observes queue admission, content-storage completion, and write
failure, but delegates both the GenAI operation and operation-span enrichment
to provider and framework instrumentations.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| external content storage | Yes — the upload hook owns the asynchronous write | ✅ Implemented |
| inference and embeddings execution or span enrichment | No — provider instrumentations own model calls and their spans | ✅ Correctly not performed |
| agent, workflow, retrieval, and tool execution | No — the util delegates these operations | ✅ Correctly not emitted |
