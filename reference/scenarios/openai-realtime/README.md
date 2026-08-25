# openai-realtime

The OpenAI Realtime API (part of the `openai` SDK) is a **model-call boundary**:
the client streams audio to and from the model over a single WebSocket session,
so it owns the server-side generations and the user's speech turns. It returns
tool calls but does not run them — the tool executes in app code, which this
scenario drives as a sibling `execute_tool` span between generations. The session
itself is not an operation; it is reported through the
`gen_ai.client.realtime_session.started` / `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — server-side generation within the Realtime session | ✅ Implemented |
| user_speech | Yes — bounded by server voice-activity events (`input_audio_buffer.speech_started` / `speech_stopped`) | ✅ Implemented |
| execute_tool | Yes — the Realtime API returns a tool call and the tool runs between generations (sibling pattern) | ✅ Implemented |
