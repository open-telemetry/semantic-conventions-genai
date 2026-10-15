# mcp

The [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) implements
both sides of the Model Context Protocol, so it owns the MCP client and server
operations and makes no model calls itself. The scenario runs an SDK client
against an SDK server ([server.py](server.py)) over stdio and records the
operation metrics in both processes from each JSON-RPC message where the SDK
hands it to, or takes it from, the transport.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| MCP client operation metrics (`mcp.client.operation.duration`, `mcp.client.operation.active`, `mcp.client.request.size`, `mcp.client.response.size`) | Yes — the SDK sends the requests and notifications | ✅ Implemented |
| MCP server operation metrics (`mcp.server.operation.duration`, `mcp.server.operation.active`, `mcp.server.request.size`, `mcp.server.response.size`) | Yes — the SDK receives and answers the requests | ✅ Implemented for requests; a notification received over stdio has no ack, and the transport can't see when its processing finishes, so the receiver doesn't record it |
| MCP session metrics (`mcp.client.session.duration`, `mcp.server.session.duration`) | Yes — the SDK owns the session | ❌ Not implemented |
| MCP client and server spans | Yes — the SDK sends and handles every message | ❌ Not implemented |

The SDK emits its own spans on the `mcp-python-sdk` tracer; the scenario drops
them. Its server spans carry `gen_ai.operation.name=execute_tool`, so they
would be counted as GenAI `execute_tool` spans and fail that span's name check.

On stdio there is no server address or application-layer protocol, so
`server.address`, `server.port`, and `network.protocol.*` are not set, and the
SDK only speaks JSON-RPC 2.0, so `jsonrpc.protocol.version` is not set either.
The scenario opts into `mcp.resource.uri` on the duration and size metrics for
its `resources/read` call, and leaves `gen_ai.prompt.variable` off the metrics
because it would put prompt argument values into their attribute sets.

A received message reaches the scenario already parsed, so its size is the
compact JSON re-serialization the conventions allow in that case. Sent messages
are measured exactly as the SDK's stdio transports write them.

MCP never answers a cancelled request. The scenario ends a request when the
`notifications/cancelled` that names it is sent or received, and records it
with `error.type` set to `cancelled`. Requests still pending when the
connection closes end with `error.type` set to `-32000`, the code the SDK fails
them with.
