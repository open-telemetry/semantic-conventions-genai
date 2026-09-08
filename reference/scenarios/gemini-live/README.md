# gemini-live

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. This scenario demonstrates the **sibling** tool-call
shape — a Gemini Live 2.x tool call surfaces as a top-level `toolCall` message,
so the generation span closes, the client runs the tool, and a second generation
speaks the answer. Running the tool is application code, not a model operation,
so it is not instrumented here; the model's request and the app's result are
captured as `tool_call` / `tool_call_response` message parts on the generations
instead. The session is reported through the
`gen_ai.client.realtime_session.started` / `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | No — the Gemini Developer API exposes no user voice-activity (VAD) events | ➖ Not instrumentable |
| execute_tool | No — the tool runs in application code; captured as `tool_call` / `tool_call_response` parts on the generations | ➖ Not instrumentable |
