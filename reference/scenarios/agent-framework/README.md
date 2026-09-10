# agent-framework

Microsoft Agent Framework is an **agent framework** with built-in OpenTelemetry
instrumentation, so this scenario turns that on
(`enable_sensitive_telemetry`) and exercises the library rather than wrapping
it. It owns agents, workflows and tool execution, and its chat clients report
the model call themselves.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — the chat client reports the model call | ✅ Implemented (native) |
| invoke_agent (internal) | Yes — `Agent.run` | ✅ Implemented (native) |
| invoke_workflow | Yes — a `WorkflowBuilder` graph run | ❌ Not implemented (the scenario runs one; the native telemetry emits no workflow span) |
| execute_tool | Yes — the framework's tool loop runs the tool | ✅ Implemented (native) |
| skills | Yes — `SkillsProvider` exposes the skill lifecycle as tools | ✅ Implemented |
