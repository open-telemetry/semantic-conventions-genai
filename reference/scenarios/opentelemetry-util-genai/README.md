# opentelemetry-util-genai

`opentelemetry-util-genai` provides shared instrumentation utilities, including
an asynchronous completion hook that stores captured GenAI content externally.
It annotates a caller-owned GenAI operation span, observes queue admission,
content-storage completion, and write failure, but delegates the GenAI operation
itself to provider and framework instrumentations.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| external content storage | Yes — the upload hook owns the asynchronous write | ✅ Implemented |
| caller-owned GenAI operation span enrichment | Yes — the hook receives and annotates the operation span | ✅ Implemented |
| inference and embeddings execution | No — provider instrumentations own model calls | ✅ Correctly not performed |
| agent, workflow, retrieval, and tool execution | No — the util delegates these operations | ✅ Correctly not emitted |
