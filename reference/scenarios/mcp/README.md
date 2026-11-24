# mcp

The `mcp` Python SDK implements the **Model Context Protocol** client and
server over JSON-RPC. It owns the `mcp.client` and `mcp.server` spans and
the `mcp.client.operation.duration` and `mcp.server.operation.duration`
metrics at the protocol request/response boundary, including tool discovery
(`tools/list`), tool calls (`tools/call`), prompt retrieval (`prompts/get`),
and resource reads (`resources/read`).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| `mcp.client` (`mcp.client.operation.duration`) | Yes — MCP client per-request boundary (`ClientSession.send_request`) | ✅ Implemented |
| `mcp.server` (`mcp.server.operation.duration`) | Yes — MCP server request boundary (`ServerMiddleware`) | ✅ Implemented |

The `tools/call` spans cover these tool results:

| Tool | `CallToolResult` | Recorded in `gen_ai.tool.call.result` |
| --- | --- | --- |
| `get_weather` | `structuredContent` and a text block that repeats it | `value` and `parts` (text) |
| `get_weather_map` | `structuredContent`, a text block that repeats it, and an image block | `value` and `parts` (text, image) |
| `get_weather_summary` | One text block | `parts` (text) |
| `get_weather_report` | A text block and an embedded `resource` block | `parts` (text); the `resource` block has no matching part type and isn't recorded |
| `missing_tool` (not on the server) | `isError` | Nothing; `error.type` = `tool_error` |
