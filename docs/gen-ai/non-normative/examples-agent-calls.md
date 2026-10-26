# Agent call examples

These examples illustrate [agent and framework spans](../gen-ai-agent-spans.md).

<!-- toc -->

- [Agent tool transfer that returns to the source](#agent-tool-transfer-that-returns-to-the-source)
- [Agent tool transfer that passes control](#agent-tool-transfer-that-passes-control)

<!-- tocstop -->

## Agent tool transfer that returns to the source

In this example, `root_agent` invokes `weather_specialist` through an agent tool
and resumes after the specialist returns. Content capturing is disabled.

**Source agent span:**

| Property | Value |
| --- | --- |
| Span name | `"invoke_agent root_agent"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"4bf92f3577b34da6a3ce929d0e0e4736"` |
| Span id | `"00f067aa0ba902b7"` |
| `gen_ai.operation.name` | `"invoke_agent"` |
| `gen_ai.agent.name` | `"root_agent"` |
| `gen_ai.request.model` | `"gemini-2.0-flash"` |

**Agent tool span:**

| Property | Value |
| --- | --- |
| Span name | `"execute_tool weather_specialist"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"4bf92f3577b34da6a3ce929d0e0e4736"` |
| Span id | `"b9c7c989f97918e1"` |
| Parent span id | `"00f067aa0ba902b7"` |
| `gen_ai.operation.name` | `"execute_tool"` |
| `gen_ai.agent.name` | `"root_agent"` |
| `gen_ai.tool.name` | `"weather_specialist"` |
| `gen_ai.tool.type` | `"function"` |
| `gen_ai.tool.call.id` | `"call_weather_1"` |
| `gen_ai.transfer.mode` | `"return_to_caller"` |
| `gen_ai.transfer.target.name` | `"weather_specialist"` |

**Target agent span:**

| Property | Value |
| --- | --- |
| Span name | `"invoke_agent weather_specialist"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"4bf92f3577b34da6a3ce929d0e0e4736"` |
| Span id | `"7b3f9e6d4a1c2058"` |
| Parent span id | `"b9c7c989f97918e1"` |
| `gen_ai.operation.name` | `"invoke_agent"` |
| `gen_ai.agent.name` | `"weather_specialist"` |
| `gen_ai.request.model` | `"gemini-2.0-flash"` |

## Agent tool transfer that passes control

In this example, `agent-a` calls a transfer tool that passes control to `agent-b`.
The enclosing workflow invokes the agents as separate steps, so their spans are
siblings. The transfer tool selects the next agent but does not invoke it.
Content capturing is disabled.

**Enclosing workflow span:**

| Property | Value |
| --- | --- |
| Span name | `"invoke_workflow sequential-agents"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"7d3a91e25c6f408ab2e019f7d4c83560"` |
| Span id | `"5d9fb1324680ace2"` |
| `gen_ai.operation.name` | `"invoke_workflow"` |
| `gen_ai.workflow.name` | `"sequential-agents"` |

**Source agent span:**

| Property | Value |
| --- | --- |
| Span name | `"invoke_agent agent-a"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"7d3a91e25c6f408ab2e019f7d4c83560"` |
| Span id | `"2a6c8e0f13579bdf"` |
| Parent span id | `"5d9fb1324680ace2"` |
| `gen_ai.operation.name` | `"invoke_agent"` |
| `gen_ai.agent.name` | `"agent-a"` |
| `gen_ai.request.model` | `"gpt-4o-mini"` |

**Transfer tool span:**

| Property | Value |
| --- | --- |
| Span name | `"execute_tool transfer_to_agent_b"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"7d3a91e25c6f408ab2e019f7d4c83560"` |
| Span id | `"3b7d9f102468ace0"` |
| Parent span id | `"2a6c8e0f13579bdf"` |
| `gen_ai.operation.name` | `"execute_tool"` |
| `gen_ai.agent.name` | `"agent-a"` |
| `gen_ai.tool.name` | `"transfer_to_agent_b"` |
| `gen_ai.tool.type` | `"function"` |
| `gen_ai.tool.call.id` | `"call_transfer_1"` |
| `gen_ai.transfer.mode` | `"pass_control"` |
| `gen_ai.transfer.target.name` | `"agent-b"` |

**Target agent span:**

| Property | Value |
| --- | --- |
| Span name | `"invoke_agent agent-b"` |
| Span kind | `INTERNAL` |
| Span status | `UNSET` |
| Trace id | `"7d3a91e25c6f408ab2e019f7d4c83560"` |
| Span id | `"4c8ea0213579bdf1"` |
| Parent span id | `"5d9fb1324680ace2"` |
| `gen_ai.operation.name` | `"invoke_agent"` |
| `gen_ai.agent.name` | `"agent-b"` |
| `gen_ai.request.model` | `"gpt-4o-mini"` |
