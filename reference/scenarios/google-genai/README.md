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
| create_agent | Yes — `google.genai.Client.agents` supports remote agent creation | ✅ Implemented |
| invoke_agent (client) | Yes — `google.genai.Client.agents` supports remote agent invocation | ❌ Not implemented |

## Media capture regression

Inline media is captured from the SDK's returned bytes and MIME type. Empty
bytes remain present; missing bytes or MIME metadata do not produce a blob.
The tests use a local `MockTransport` and in-memory OTel exporters:

```bash
uv run --frozen --python 3.12 python -B -m unittest -v test_media_capture
```

Run from this directory. CI runs these tests before the Google GenAI
conformance scenario.
