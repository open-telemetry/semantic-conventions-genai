# Agent-to-agent interaction examples

This page illustrates how existing GenAI spans represent agent-to-agent
interactions. These examples are non-normative.

## Tool-based transfer

Some frameworks expose another agent as a tool. The framework records the tool
execution as an `execute_tool` span:

- `gen_ai.agent.*` identifies the source agent executing the tool.
- `gen_ai.transfer.target.*` identifies the target agent.
- `gen_ai.transfer.mode` describes whether control returns to the source agent
  or passes to the target.

The target agent's execution can be recorded as a separate `invoke_agent`
INTERNAL span when it is observable.

```mermaid
flowchart LR
  subgraph P["PROCESS: multi-agent runtime"]
    direction LR
    subgraph S["SOURCE AGENT"]
      S1["invoke_agent source [INTERNAL]"]
      S2["execute_tool transfer [INTERNAL]<br/>agent.name = source<br/>transfer.mode = return_to_caller<br/>transfer.target.type = agent<br/>transfer.target.name = target"]
      S1 --> S2
    end
    subgraph T["TARGET AGENT"]
      T1["invoke_agent target [INTERNAL]"]
    end
    S2 --> T1
  end
```

For a transfer that does not return control to the source agent, the
`execute_tool` span instead records:

| Property | Value |
| --- | --- |
| `gen_ai.agent.name` | `"source"` |
| `gen_ai.transfer.mode` | `"pass_control"` |
| `gen_ai.transfer.target.name` | `"target"` |
| `gen_ai.transfer.target.type` | `"agent"` |

## Agent invocation through an API or protocol

When an agent invokes another agent through an API or protocol, use the existing
`invoke_agent` CLIENT span. `gen_ai.agent.*` identifies the invoked agent;
`gen_ai.transfer.*` is not recorded.

For example, Google ADK's `RemoteA2aAgent` can discover a remote agent from its
Agent Card and invoke it with the A2A protocol's `SendMessage` operation.
The local `RemoteA2aAgent` execution is an `invoke_agent` INTERNAL span, and the
protocol request is its `invoke_agent` CLIENT child.

The target process can independently record the agent's execution as an
`invoke_agent` INTERNAL span. When trace context is propagated, that execution
can be a descendant of the CLIENT span.

```mermaid
flowchart LR
  subgraph C["CALLER PROCESS"]
    C1["invoke_agent source [INTERNAL]"]
    C2["invoke_agent target [CLIENT]<br/>agent.name = target"]
    C1 --> C2
  end
  subgraph T["TARGET PROCESS"]
    T1["invoke_agent target [INTERNAL]"]
  end
  C2 --> T1
```

These conventions do not require the target execution span or prescribe a
particular context-propagation mechanism.
