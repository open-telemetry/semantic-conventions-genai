# adk_a2a

Google ADK serves an agent over A2A and delegates model calls to its Gemini client. The scenario invokes the served agent with a real A2A client.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| Client operation duration | No, model calls belong to the Gemini client | Suppressed |

ADK's native `gen_ai.client.operation.duration` measures inference. The scenario suppresses it because inference duration belongs on `gen_ai.client.inference.duration` in the Gemini client.
