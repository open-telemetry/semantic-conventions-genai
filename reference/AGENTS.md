# Authoring reference scenarios

Two steps:

1. **Decide what the library supports** — run the litmus tests below to figure
   out which operations (spans, metrics, events) a library can legitimately
   emit.
2. **Implement them in a reference scenario** — emit only those operations, then
   regenerate the data and reports.

For per-scenario authoring rules, see
[../.github/instructions/reference-scenarios.instructions.md](../.github/instructions/reference-scenarios.instructions.md).

## Step 1 — Decide what the library supports

A scenario emits telemetry only for operations the library itself performs. If
library A delegates an operation to another (also instrumentable) library B, do
**not** instrument that call in library A — it belongs to B.

**Fact-check against the library's real API reference.** Do not guess what a
library does or doesn't support from its name or reputation. Before deciding an
operation is in or out of scope, confirm it against the library's official API
docs — many SDKs cover more than their obvious use case (e.g. `openai` has
retrieval via vector stores / file search and conversation state, not just
inference). Describe each operation in terms of the concrete API that backs it.

Run each litmus test to decide which operations apply.

### Model call (inference / embeddings)

Before emitting an inference (`chat`) or `embeddings` span — or an
inference-operation-details event — ask:

> Does this library delegate the actual model call to another instrumentable
> library (e.g. `openai`, `litellm`, `google-genai`)?

- **Yes** → do **not** emit inference or embeddings (span or event). It belongs
  to the underlying LLM library. Emit only framework-owned operations
  (`invoke_agent`, `invoke_workflow`, `plan`, `execute_tool`, `retrieval`).
- **No** (the library is itself the model-call boundary — it calls the model
  directly, or owns it across a process boundary no in-process instrumentable
  library can observe) → emit it, and correlate via standard context
  propagation.

### Tool execution

> Does the library execute the tool itself — i.e. does it provide a
> tool-execution helper (automatic function calling, an agent/tool runner) that
> invokes the tool and feeds the result back?

- **Yes** (e.g. `google-genai` / `vertexai` automatic function calling, agent
  frameworks that run tools) → `execute_tool` is instrumentable here; emit it.
- **No** (the client only returns tool calls and the tool runs in application
  code the library never sees) → `execute_tool` is **not instrumentable** by
  this library. Do not emit it from a model-client scenario; a span around the
  app's own function is not something generic instrumentation of the client
  could produce.

### Client invoke / create agent

> Does this library create and invoke remote AI agents (e.g. AWS Bedrock Agent
> or OpenAI Assistants)?

- **Yes** → emit client spans for create and invoke agent operations.
- **No** → do not emit client agent spans. If the library implements agentic or
  other AI scenarios, check the internal invoke agent or workflow tests instead.

### Internal invoke agent

> Does the library have a concept of an AI agent?

- **Yes** → emit an internal invoke agent span only for scenarios that use the
  library's agent API.
- **No** (no formal agent concept, or the AI scenario doesn't involve agents) →
  check the workflow test instead.

### Workflow

> Does the library have a concept of an AI workflow or graph — an operation that
> combines arbitrary AI-related operations such as agent invocations, chained
> LLM calls, and other auxiliary operations?

- **Yes** → emit a workflow span around the library API that invokes the
  workflow.
- **No** → don't emit a workflow span. A single agent run or a plain chain of
  calls is not an AI workflow.

## Step 2 — Implement in a reference scenario

Emit only the operations the litmus tests identified as supported, then
regenerate the data and reports:

```bash
uv run run-scenario <library>   # regenerate scenarios/<library>/data.json
uv run update-reports           # refresh README status tables
```
