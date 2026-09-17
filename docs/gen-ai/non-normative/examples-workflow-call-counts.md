# Workflow call count examples

<!-- toc -->

- [Counting calls in nested workflows](#counting-calls-in-nested-workflows)

<!-- tocstop -->

## Counting calls in nested workflows

A call made in a nested workflow is recorded against its own workflow
execution and every enclosing workflow execution. With one level of nesting,
such a call is counted twice, once by each execution.

Frameworks nest workflows in different ways: a sub-graph invoked as a node of
another graph, or a workflow that an outer agent invokes through one of its
tools. Either way, the inner execution runs to completion inside the outer one.

The outer workflow `research_assistant` runs a `planner` agent. The planner
makes an inference call that asks for a tool, and that tool invokes the inner
workflow `web_research`. `web_research` runs a `researcher` agent, which makes
an inference call asking for `get_weather`, runs it, then makes a second
inference call to answer. Control returns to the planner, which makes a second
inference call of its own to answer the user.

Each execution records its count when it ends, the inner one first:

| Metric                                   | `gen_ai.workflow.name` | Recorded value |
| ---------------------------------------- | ---------------------- | -------------- |
| `gen_ai.invoke_workflow.inference_calls` | `web_research`         | 2              |
| `gen_ai.invoke_workflow.tool_calls`      | `web_research`         | 1              |
| `gen_ai.invoke_workflow.inference_calls` | `research_assistant`   | 4              |
| `gen_ai.invoke_workflow.tool_calls`      | `research_assistant`   | 2              |

`web_research` reports only what ran inside it: the researcher's 2 inference
calls and its 1 call to `get_weather`. The planner's call to `web_research`
started that execution from outside, so it counts for `research_assistant`
alone.

`research_assistant` reports 4 inference calls (the planner's 2 and the
researcher's 2) and 2 tool calls: the planner's call to `web_research` and the
researcher's call to `get_weather`. If `web_research` had used no tools, it
would still record `gen_ai.invoke_workflow.tool_calls` as 0.

The run made 4 inference calls and 2 tool calls, while the recorded workflow
counts total 6 inference calls and 3 tool calls. Summing across
`gen_ai.workflow.name` over-counts by the calls made in nested workflows.

The agent grain does not double count. The same run records:

| Metric                                | `gen_ai.agent.name` | Recorded value |
| ------------------------------------- | ------------------- | -------------- |
| `gen_ai.invoke_agent.inference_calls` | `planner`           | 2              |
| `gen_ai.invoke_agent.tool_calls`      | `planner`           | 1              |
| `gen_ai.invoke_agent.inference_calls` | `researcher`        | 2              |
| `gen_ai.invoke_agent.tool_calls`      | `researcher`        | 1              |

Every call an agent makes belongs to exactly one agent invocation, whichever
workflow it ran in, so the agent rows sum to the outer workflow's 4 and 2.
Calls made outside any agent, such as a graph's routing steps, are counted at
workflow grain only.

The `openai-agents` reference scenario under `reference/scenarios/` runs this
example and records both tables.

For consumers:

- Pick the outermost workflow to cover a whole run, or an inner one to isolate
  a reusable sub-workflow. Nothing marks which is which yet, so a workflow
  that sometimes runs standalone and sometimes runs nested contributes to the
  same series either way. Once `gen_ai.main_agent.name` is available, a nested
  execution is identified by its presence.
- To count each agent's calls exactly once across a run, use the
  `gen_ai.invoke_agent.*` counterparts. They do not cover calls made outside an
  agent.
- An inner and outer workflow that record the same `gen_ai.workflow.name`, or
  that both omit it, land in one time series. That series then holds both
  executions, summing to 6 inference calls for the run above, with no
  attribute left to tell the outer execution from the inner one.
