# adk_a2a

This scenario serves a Google ADK agent over A2A and invokes it through the A2A
client. ADK emits the native telemetry for its agent execution.

The scenario configures the native `gen_ai.invoke_agent.duration` histogram
with the recommended decimal buckets.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| invoke_agent (internal) | Yes - ADK runs the agent | Implemented by ADK |
| invoke_agent duration | Yes - ADK times agent runs | Implemented natively with decimal buckets |
