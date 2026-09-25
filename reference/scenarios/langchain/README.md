# langchain

LangChain is an **orchestration framework**. It delegates the actual model call
to the underlying LLM client (e.g. `openai`), so it does **not** own inference —
that belongs to the LLM library and is captured as a child span. LangChain owns
the framework operations it performs directly: retrieval, planning, and tool
execution.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| invoke_workflow | Yes — chain/graph execution | ✅ Implemented |
| invoke_agent (internal) | Yes — `create_agent` agent run | ✅ Implemented |
| retrieval | Yes — retriever runs the retrieval | ✅ Implemented |
| plan | Yes — Plan-and-Execute planning phase | ✅ Implemented |
| execute_tool | Yes — `BaseTool.invoke()` runs the tool | ✅ Implemented |
| workflow inference/tool call counts | Yes — graph-scoped model/tool start callbacks | ✅ Implemented |

The outer `Weather graph` invokes the `Weather research` subgraph twice. Each
subgraph invocation records its own totals; inherited callbacks count both
invocations in the outer workflow. Each invocation records in a `finally`, so a
failed run still reports.
