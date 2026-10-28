# gemini-live

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. In this scenario, Gemini Live 2.5 reports the tool call
as the end of a generation, so the application sends the tool result and a
second generation speaks the answer. The tool request and response are recorded
as `tool_call` and `tool_call_response` message parts. The application executes
the tool, so this client scenario does not emit an `execute_tool` span. The
session is reported through the
`gen_ai.client.realtime_session.started` / `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | Yes - bounded by server voice-activity events (`voice_activity` `ACTIVITY_START` / `ACTIVITY_END`) | ✅ Implemented |
| execute_tool | No — the tool runs in application code; captured as `tool_call` / `tool_call_response` parts on the generations | ➖ Not instrumentable |
