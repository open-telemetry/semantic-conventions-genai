# agent-framework

Microsoft Agent Framework owns the agent run, tool execution, and pre-execution
tool approval decisions it exposes through its agent runtime. The OpenAI client
used by this scenario is configured against the repository mock endpoint.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — the Agent Framework OpenAI client owns the model call | ✅ Implemented |
| invoke_agent (internal) | Yes — `Agent.run()` owns the agent invocation | ✅ Implemented |
| execute_tool | Yes — Agent Framework invokes function tools | ✅ Implemented |
| tool call decision (event) | Yes — `approval_mode="always_require"` exposes approval before execution | ✅ Implemented |
