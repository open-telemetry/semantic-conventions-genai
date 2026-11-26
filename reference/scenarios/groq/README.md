# groq

The `groq` client is a **model-call boundary**: it calls the model directly, so
it owns inference. Groq's API has no embeddings endpoint, so embeddings is out
of scope. Tool calling is supported, with the tool itself running in application
code.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| execute_tool | No — the client returns tool calls but doesn't execute them; the tool runs in app code | ➖ Not instrumentable |

Groq gives no modality breakdown, so the usage counters use `unknown`.
Cached input and reasoning output counts from `prompt_tokens_details` and
`completion_tokens_details` feed the cache-read and reasoning counters when
Groq reports them.

The basic chat scenario records Groq's response service tier on duration and
token metrics when Groq returns it.

The streaming-only conformance cases use Groq SDK chunks with usage in
`x_groq.usage`. A terminal `x_groq.error` chunk sets `error.type` on the span,
operation histograms, and usage counters for reported token counts.
