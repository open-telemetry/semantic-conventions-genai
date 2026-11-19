# mcp

The `mcp` Python SDK implements the **Model Context Protocol** client and
server over JSON-RPC. It owns the `mcp.client` and `mcp.server` spans and
the MCP client and server operation metrics (`mcp.client.operation.duration`,
`mcp.client.operation.active`, `mcp.server.operation.duration`, and
`mcp.server.operation.active`) at the protocol request/response boundary,
including tool discovery (`tools/list`), tool calls (`tools/call`), prompt
retrieval (`prompts/get`), and resource reads (`resources/read`).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| `mcp.client` (`mcp.client.operation.duration`, `mcp.client.operation.active`) | Yes — MCP client per-request boundary (`ClientSession.send_request`) | ✅ Implemented |
| `mcp.server` (`mcp.server.operation.duration`, `mcp.server.operation.active`) | Yes — MCP server request boundary (`ServerMiddleware` + ASGI response completion) | ✅ Implemented |
