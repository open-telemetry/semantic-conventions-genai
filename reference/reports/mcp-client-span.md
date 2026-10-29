# MCP Client Span

> **[Semantic Convention](../../docs/gen-ai/mcp.md#client)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| mcp.method.name | [mcp] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.prompt.name | (none) |
| gen_ai.tool.name | [mcp] |
| jsonrpc.request.id | [mcp] |
| mcp.resource.uri | (none) |
| rpc.response.status_code | [mcp] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [mcp] |
| jsonrpc.protocol.version | (none) |
| mcp.protocol.version | [mcp] |
| mcp.session.id | [mcp] |
| network.protocol.name | [mcp] |
| network.protocol.version | (none) |
| network.transport | [mcp] |
| server.address | [mcp] |
| server.port | [mcp] |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.prompt.variable | (none) |
| gen_ai.tool.call.arguments | [mcp] |
| gen_ai.tool.call.result | [mcp] |

[mcp]: ../scenarios/mcp/scenario.py
