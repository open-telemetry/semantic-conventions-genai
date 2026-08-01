# anthropic

The `anthropic` client is a **model-call boundary**: it calls the Messages API
directly, so it owns inference. The API has no embeddings endpoint (Anthropic
points users to third-party embedding providers), so embeddings is out of scope.
Tool use is supported, but the tool itself runs in application code.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — Messages API, calls the model directly | ✅ Implemented |
| execute_tool | No — the Messages API returns tool-use requests but doesn't execute tools; the tool runs in app code | ➖ Not instrumentable |
