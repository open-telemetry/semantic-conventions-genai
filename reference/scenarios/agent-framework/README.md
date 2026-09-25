# agent-framework

Microsoft Agent Framework owns agent execution, workflows, and tool calls.
Its OpenAI chat clients delegate model requests to the OpenAI SDK. Native
telemetry also emits model-call spans and duration measurements; this scenario
publishes those durations as `gen_ai.client.inference.duration` with an OTel SDK view.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No - the OpenAI SDK owns the model request | Native telemetry emits it |
| invoke_agent (internal) | Yes - `Agent.run` executes the agent | Implemented |
| execute_tool | Yes - the framework invokes the registered tool | Implemented |
| invoke_workflow | Yes - `WorkflowBuilder` runs the agent workflow | Implemented |
