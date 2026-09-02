# opentelemetry-util-genai

`opentelemetry-util-genai` provides shared instrumentation utilities, including
an asynchronous completion hook that stores captured GenAI content externally.
It observes queue admission, content-storage completion, and write failure but
delegates the GenAI operation itself to provider and framework instrumentations.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| external content storage | Yes — the upload hook owns the asynchronous write | ✅ Implemented |
| inference and embeddings | No — provider instrumentations own model calls | ✅ Correctly not emitted |
| agent, workflow, retrieval, and tool execution | No — the util delegates these operations | ✅ Correctly not emitted |
