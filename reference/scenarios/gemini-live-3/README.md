# gemini-live-3

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. This scenario records one spoken response as a
`realtime_inference` span. The session is reported through the
`gen_ai.client.realtime_session.started` and `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | Yes — bounded by server voice-activity events (`voice_activity` `ACTIVITY_START` / `ACTIVITY_END`) | ✅ Implemented |
| execute_tool | No — the application executes the tool outside the client library | ➖ Not instrumentable |
