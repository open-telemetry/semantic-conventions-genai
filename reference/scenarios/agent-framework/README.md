# agent-framework

Microsoft Agent Framework defines and runs in-process agents and workflows. Its
explicit agent `id` is available to instrumentation and can identify durable
agent definitions independently of display names or runtime instances.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| invoke_agent (internal) | Yes - `Agent.run` invokes a defined agent | ✅ Implemented |
| invoke_agent duration | Yes - `Agent.run` bounds the invocation | ✅ Implemented |
| execute_tool | Yes - the framework runs registered tools | ✅ Implemented |
| invoke_workflow | Yes - `Workflow.run` executes a multi-agent workflow | ✅ Implemented |
| inference (`chat`) | Yes - the framework's OpenAI clients issue the model request | ✅ Implemented |
