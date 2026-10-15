# MCP Client Operation Duration Metric

> **[Semantic Convention](../../docs/gen-ai/mcp.md#metric-mcpclientoperationduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| mcp.method.name | [mcp] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.prompt.name | [mcp] |
| gen_ai.tool.name | [mcp] |
| rpc.response.status_code | [mcp] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [mcp] |
| jsonrpc.protocol.version | (none) |
| mcp.protocol.version | [mcp] |
| network.protocol.name | (none) |
| network.protocol.version | (none) |
| network.transport | [mcp] |
| server.address | (none) |
| server.port | (none) |

## Opt-In

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.prompt.variable | (none) |
| mcp.resource.uri | [mcp] |

[mcp]: ../scenarios/mcp/scenario.py
