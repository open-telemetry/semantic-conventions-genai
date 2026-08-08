# langchain

LangChain is an **orchestration framework**. It delegates the actual model call
to the underlying LLM client (e.g. `openai`), so it does **not** own inference —
that belongs to the LLM library and is captured as a child span. LangChain owns
the framework operations it performs directly: retrieval, planning, and tool
execution.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| invoke_workflow | Yes — chain/graph execution | ❌ Not implemented |
| retrieval | Yes — retriever runs the retrieval | ✅ Implemented |
| plan | Yes — Plan-and-Execute planning phase | ✅ Implemented |
| execute_tool | Yes — `BaseTool.invoke()` runs the tool | ✅ Implemented |
