# mcp

The `mcp` Python SDK implements the **Model Context Protocol** client and
server over JSON-RPC. It owns the `mcp.client` and `mcp.server` spans and
the MCP client and server operation metrics (`duration`, `active`,
`request.message.size`, and `response.message.size`) at the protocol and
Streamable HTTP transport boundaries, including tool discovery (`tools/list`),
tool calls (`tools/call`), prompt retrieval (`prompts/get`), and resource reads
(`resources/read`).

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| `mcp.client` (`mcp.client.operation.duration`, `mcp.client.operation.active`, `mcp.client.request.message.size`, `mcp.client.response.message.size`) | Yes — MCP client per-request and HTTP transport boundary (`ClientSession.send_request` + HTTP transport) | ✅ Implemented |
| `mcp.server` (`mcp.server.operation.duration`, `mcp.server.operation.active`, `mcp.server.request.message.size`, `mcp.server.response.message.size`) | Yes — MCP server request and ASGI transport boundary (`ServerMiddleware` + ASGI wrapper) | ✅ Implemented |
