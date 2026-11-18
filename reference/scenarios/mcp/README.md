# mcp

The `mcp` Python SDK implements the **Model Context Protocol** client and
server over JSON-RPC. It owns the `mcp.client` and `mcp.server` spans and
the `mcp.client.operation.duration` and `mcp.server.operation.duration`
metrics at the protocol request/response boundary, including tool calls
(`tools/call`), prompt retrieval (`prompts/get`), and resource reads
(`resources/read`).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| `mcp.client` (`mcp.client.operation.duration`) | Yes — MCP client request boundary (`ClientSession.call_tool`, `get_prompt`, `read_resource`) | ✅ Implemented |
| `mcp.server` (`mcp.server.operation.duration`) | Yes — MCP server request boundary (`ServerMiddleware`) | ✅ Implemented |
