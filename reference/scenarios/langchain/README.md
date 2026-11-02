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
| execute_tool (command) | Yes — `ShellToolMiddleware`'s `shell` tool runs a general command | ✅ Implemented |

The tool execution error handlers, including shell commands, record a correlated
`gen_ai.execute_tool.exception` WARN log and rethrow the exception. This scenario
does not exercise those paths.

The internal agent invocation error handler records a correlated
`gen_ai.invoke_agent.exception` WARN log and rethrows the exception. This scenario
does not exercise that path.
