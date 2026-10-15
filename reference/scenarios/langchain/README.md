# langchain

LangChain is an **orchestration framework**. It delegates the actual model call
to the underlying LLM client (e.g. `openai`), so it does **not** own inference —
that belongs to the LLM library and is captured as a child span. LangChain owns
the framework operations it performs directly: retrieval, planning, and tool
execution.

The tool-handoff graph registers the compiled `create_agent()` agents directly.
Instrumentation resolves `Command.goto` through the parent graph's registered
node and checks the SDK's `langchain_create_agent` metadata before recording an
agent transfer. Ordinary nodes and workflow subgraphs do not qualify.

The source and target spans record finish reasons and token usage from their
own `AIMessage` objects. They share the named graph span, and the scenario checks
that the source invocation ends before the target starts. LangGraph handles
`Command.PARENT` itself, without an application wrapper routing the command.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| invoke_workflow | Yes — chain/graph execution | ✅ Implemented |
| invoke_agent (internal) | Yes — `create_agent` agent run | ✅ Implemented |
| retrieval | Yes — retriever runs the retrieval | ✅ Implemented |
| plan | Yes — Plan-and-Execute planning phase | ✅ Implemented |
| execute_tool | Yes — `BaseTool.invoke()` runs the tool | ✅ Implemented |
| execute_tool (command) | Yes — `ShellToolMiddleware`'s `shell` tool runs a general command | ✅ Implemented |
