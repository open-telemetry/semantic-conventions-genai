# mcp

The MCP Python SDK implements both sides of the Model Context Protocol. The
scenario runs an `MCPServer` and a `Client` in one process, connected over
Streamable HTTP with the `initialize` handshake, and records the MCP client and
server spans. The SDK emits its own spans; the scenario turns them off and
records the reference spans in their place.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| MCP client span for requests | Yes — `ClientSession.send_request` sends every request; the Streamable HTTP transport knows the request ID, session ID and server address | ✅ Implemented |
| MCP client span for notifications | Yes — `ClientSession.send_notification` sends them | ❌ Not implemented |
| MCP server span | Yes — server middleware wraps every inbound message | ✅ Implemented |
| MCP metrics | Yes — same boundaries as the spans | ❌ Not implemented |

The `tools/call` spans cover these tool results:

| Tool | `CallToolResult` | Recorded |
| --- | --- | --- |
| `get_weather` | `structuredContent` and a text block that repeats it | `gen_ai.tool.call.result` |
| `get_weather_map` | `structuredContent`, a text block that repeats it, and an image block | `gen_ai.tool.call.result` and `gen_ai.tool.call.result_parts` |
| `get_weather_summary` | One text block | `gen_ai.tool.call.result` as a string |
| `get_tides` (not on the server) | `isError` | `error.type` = `tool_error`, no result |
| `get_weather_alerts` | JSON-RPC error | `error.type` and `rpc.response.status_code` |
