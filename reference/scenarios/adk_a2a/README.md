# adk_a2a

Google ADK serves an agent over A2A and delegates model calls to its Gemini client. The scenario invokes the served agent with a real A2A client.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| Client operation duration | Yes - ADK's native instrumentation times the Gemini call | ✅ Implemented |

ADK records model call timings and attributes on a reference `gen_ai.client.operation.duration` histogram created with the recommended bucket advice.
