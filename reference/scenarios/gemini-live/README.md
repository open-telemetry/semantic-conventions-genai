# gemini-live

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. In this scenario, Gemini Live 2.5 reports the tool call
as the end of a generation, so the application sends the tool result and a
second generation speaks the answer. The tool request and response are recorded
as `tool_call` and `tool_call_response` message parts. The application executes
the tool, so this client scenario does not emit an `execute_tool` span. The
scenario also covers a generation interrupted by user barge-in. Generation
spans start and end from Gemini's `server_content` completion and interruption
signals, while one dispatcher preserves interleaved voice activity,
transcription, output, and usage messages. The user-speech span is kept at
session scope because the SDK ends a generation's receive iterator at
`turn_complete`, before a later `ACTIVITY_END` can arrive. It uses
`turn_complete_reason` when the provider supplies one. The session is reported
through the `gen_ai.client.realtime_session.started` / `.ended` events,
including an SDK-visible connection failure on active speech and generation
spans.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | Yes - bounded by server voice-activity events (`voice_activity` `ACTIVITY_START` / `ACTIVITY_END`) | ✅ Implemented |
| execute_tool | No — the tool runs in application code; captured as `tool_call` / `tool_call_response` parts on the generations | ➖ Not instrumentable |
