# MCP Client Operation Active Metric

> **[Semantic Convention](../../docs/gen-ai/mcp.md#metric-mcpclientoperationactive)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| mcp.method.name | [mcp] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.prompt.name | [mcp] |
| gen_ai.tool.name | [mcp] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [mcp] |
| jsonrpc.protocol.version | (none) |
| mcp.protocol.version | [mcp] |
| network.protocol.name | [mcp] |
| network.protocol.version | [mcp] |
| network.transport | [mcp] |
| server.address | [mcp] |
| server.port | [mcp] |

[mcp]: ../scenarios/mcp/scenario.py
