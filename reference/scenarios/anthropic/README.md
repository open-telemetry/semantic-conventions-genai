# anthropic

The `anthropic` client is a **model-call boundary**: it calls the Messages API
directly, so it owns inference. The API has no embeddings endpoint (Anthropic
points users to third-party embedding providers), so embeddings is out of scope.
Tool use is supported, but the tool itself runs in application code.

The same client also drives the **Managed Agents** service (`beta.agents`,
`beta.sessions`, `beta.memory_stores`), where agents run server-side. The client
owns the create-agent and invoke-agent client operations; the agent's reasoning,
model calls, and tool execution happen across a process boundary it cannot
observe.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — Messages API, calls the model directly | ✅ Implemented |
| execute_tool | No — the Messages API returns tool-use requests but doesn't execute tools; the tool runs in app code | ➖ Not instrumentable |
| create_agent | Yes — Managed Agents `beta.agents.create` | ✅ Implemented |
| invoke_agent (client) | Yes — a Managed Agents session runs the remote agent | ❌ Not implemented |
| memory | Yes — Managed Agents memory stores | ❌ Not implemented |

`invoke_agent` needs care: `beta.sessions.events.send` only queues the user
event and returns the accepted events. The agent then runs asynchronously (the
session reports `running`) and its output arrives over
`beta.sessions.events.stream`, so output messages and usage are not available
when the send call returns.

## Inline media byte sizes

The image and PDF calls demonstrate the optional `BlobPart.byte_size` proposed
in [#143](https://github.com/open-telemetry/semantic-conventions-genai/pull/143).
The size comes from decoding the inline `source.data` passed to the Messages API:
20 image bytes and 48 PDF bytes, not the 28 and 64 base64 characters. No file or
URI is fetched to discover a size. Sizes that are not observable stay absent.

The pinned util-genai version has no `byte_size` field on `Blob`, so these calls
use dict parts with its existing span/event serialization, as the compaction
scenario already does. This is manual reference telemetry, not automatic
Anthropic instrumentation support.

Run the local-mock regressions from this directory:

```bash
uv run --frozen --python 3.12 python -m unittest test_inline_byte_size -v
```

From the repository root, run `make test-anthropic`. CI runs this target for
the Anthropic scenario before running its conformance check.
