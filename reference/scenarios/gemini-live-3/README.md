# gemini-live-3

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. In this scenario, Gemini reports the tool request and
spoken answer within one generation, so the `realtime_inference` span remains
open across the tool exchange. The SDK exposes the tool request and response,
which are recorded as `tool_call` and `tool_call_response` message parts.
The application executes the tool, so this client scenario does not emit an
`execute_tool` span. The session is reported through the
`gen_ai.client.realtime_session.started` and `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | No — the Gemini Developer API exposes no user voice-activity (VAD) events | ➖ Not instrumentable |
| execute_tool | No — the application executes the tool outside the client library | ➖ Not instrumentable |
