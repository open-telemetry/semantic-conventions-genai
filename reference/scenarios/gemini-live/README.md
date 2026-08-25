# gemini-live

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. This scenario demonstrates the **sibling** tool-call
shape — a Gemini Live 2.x tool call surfaces as a top-level `toolCall` message,
so the generation span closes, the tool runs as a sibling `execute_tool` span,
and a second generation speaks the answer. The session is reported through the
`gen_ai.client.realtime_session.started` / `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | No — the Gemini Developer API exposes no user voice-activity (VAD) events | ➖ Not instrumentable |
| execute_tool | Yes — the tool runs between generations (sibling pattern) | ✅ Implemented |
