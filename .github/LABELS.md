# Label Definitions

## `area:*`

### `area:agent`

A single agent invocation: agent identity and configuration, the
agent's reasoning/planning loop, and anything scoped to the behavior
of one agent run.

### `area:agent-orchestration`

How agents, workflows, and tasks compose above the single-agent layer:
workflow execution, handoffs, delegation, and anything that spans more
than one agent invocation.

### `area:embeddings`

Embedding requests and their results.

### `area:evaluation`

Evaluation of GenAI runs: evaluator identity, evaluation runs, scores
and verdicts, and how evaluation results relate to the runs they
evaluate.

### `area:inference`

A single LLM call: model identity, request parameters, response and
finish information, and choices. Tool-call and message payloads
carried by an inference call belong under `area:tools` and
`area:messages`; apply those alongside `area:inference` when relevant.

### `area:mcp`

Conventions in the `mcp.*` namespace: anything MCP-specific, including
MCP transport, MCP tool listing and approval, and MCP-flavored
extensions of GenAI semantics. MCP-transport-specific tool semantics
belong here; generic tool-call shape belongs under `area:tools`. Apply
both when both apply.

### `area:memory`

Agent memory: memory store operations, memory record lifecycle, memory
search, and the memory-layer taxonomy. When a memory layer is
implemented over a vector store, use `area:memory` for memory-API-level
concerns and `area:retrieval` for the underlying vector-store
semantics; apply both when both apply.

### `area:messages`

Shape and content of input and output messages: message and message-part
structure, system instructions, content modalities (text, image,
audio, video, file), citations, reasoning content, and prompt templates.

### `area:retrieval`

Retrieval and vector databases: retrieval operations and the structure
of returned documents and scores.

### `area:streaming`

Telemetry that exists only for streamed responses: time-to-first-token
(or first-chunk), time-per-output-token, inter-token-latency, and
partial-stream events. Non-streaming latency belongs under the
relevant area, not here.

### `area:tokens`

Token usage: input and output token counts, breakdowns (e.g. cached,
reasoning), per-modality splits, and total-token aggregation.

### `area:tools`

Tool definitions and tool calls: how tools are declared, how tool
calls and tool results are executed and recorded, and the shape of
tool-call and tool-result content carried in messages.
