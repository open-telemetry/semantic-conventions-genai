# langgraph

LangGraph is a graph orchestration runtime. It owns graph execution,
checkpointing, interrupts, resumed execution, and runtime state updates.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| invoke_workflow | Yes — `StateGraph` executes the graph | ✅ Implemented |
| execution state changed event | Yes — streamed node updates expose runtime-owned deltas | ✅ Implemented |

The scenario compiles a `StateGraph` with `InMemorySaver`. Its first public
`graph.ainvoke()` returns an `interrupt()`; a later public
`graph.astream(Command(resume=...), stream_mode="updates")` resumes the
persisted execution and exposes the resulting node delta. The event records
the bounded `ExecutionState` key, delta count, and resulting
`StateSnapshot.config` checkpoint ID. It does not export state values,
execution identifiers, interrupt/resume values, or reasoning content.
