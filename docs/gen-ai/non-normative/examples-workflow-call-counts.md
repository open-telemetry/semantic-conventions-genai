# Workflow call count examples

<!-- toc -->

- [Counting calls in nested workflows](#counting-calls-in-nested-workflows)

<!-- tocstop -->

## Counting calls in nested workflows

A call made in a nested workflow is recorded against its own workflow
execution and every enclosing workflow execution.

The LangChain reference scenario (`reference/scenarios/langchain/scenario.py`)
runs an outer `Weather graph` that invokes the application-defined
`Weather research` subgraph twice. Each subgraph invocation runs a weather
agent and a formatting step. The agent makes an inference call requesting
`get_weather`, executes that tool, and makes a second inference call to answer.
The formatting step makes no model or tool calls.

Each execution records its counts when it ends:

| Workflow execution | `gen_ai.workflow.name` | `gen_ai.invoke_workflow.inference_calls` | `gen_ai.invoke_workflow.tool_calls` |
| --- | --- | --- | --- |
| First subgraph invocation | `Weather research` | 2 | 1 |
| Second subgraph invocation | `Weather research` | 2 | 1 |
| Enclosing graph | `Weather graph` | 4 | 2 |

The two subgraph invocations contribute separate histogram measurements to
the same `Weather research` series. The outer graph includes both invocations,
so it records 4 inference calls and 2 tool calls. An enclosing execution also
counts any calls it makes directly, outside a nested workflow; `Weather graph`
makes none, so its totals here come entirely from the two nested executions.

The run made 4 inference calls and 2 tool calls, while the workflow histogram
sums across both names total 8 and 4. The nested calls appear in both scopes.
A workflow execution with no calls still records zero.

For consumers:

- Select a known outermost workflow to measure a whole run, or an inner
  workflow to measure a reusable subgraph. These metrics have no attribute
  identifying whether an execution is nested.
- If a workflow sometimes runs standalone and sometimes nested, both kinds
  of execution contribute to the same series.
- If the inner and outer workflows use the same name, or both omit it, their
  measurements cannot be separated by attributes.
