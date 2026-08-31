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

The durable-workflow proof uses a LangGraph `StateGraph` compiled with
`InMemorySaver`. Its first public `graph.ainvoke()` returns an `interrupt()`;
a later public `graph.ainvoke(Command(resume=...))` resumes the persisted
workflow. Each invocation has a separate workflow span, so no span stays open
while work is suspended. After resumption, the workflow node returns one state
update. The proof reads the node delta from public `graph.astream(...,
stream_mode="updates")` output and the state version from the resulting public
`StateSnapshot.metadata`, then emits one OpenTelemetry event/log record while
the resumed workflow span is current.
The event records the bounded key name, delta size, and runtime state version,
never the state value. The proof uses `Runtime.execution_info` only to verify
that LangGraph resumed the same execution; those identifiers are not emitted.
It does not export graph state, interrupt/resume values, tool arguments or
results, idempotency data, or reasoning content.
