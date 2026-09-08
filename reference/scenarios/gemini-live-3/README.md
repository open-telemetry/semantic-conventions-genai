# gemini-live-3

The Gemini Live API, reached through `google-genai`'s
`client.aio.live.connect`, is a **model-call boundary**: the client streams audio
to and from the model over a bidirectional WebSocket session, so it owns the
server-side generations. This scenario demonstrates the **child** tool-call shape
— a Gemini Live 3.x tool call is resolved within a single generation, so the
`realtime_inference` span stays open across the whole tool round-trip. Running the
tool is application code, not a model operation, so it is not instrumented here;
and because the exchange happens inside one generation (not across two), it is
not surfaced as `tool_call` / `tool_call_response` parts either — an honest
capture gap that complements the sibling shape shown by the `gemini-live` and
`openai-realtime` scenarios. The session is reported through the
`gen_ai.client.realtime_session.started` / `.ended` events.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| realtime_inference | Yes — calls the Live API directly | ✅ Implemented |
| user_speech | No — the Gemini Developer API exposes no user voice-activity (VAD) events | ➖ Not instrumentable |
| execute_tool | No — the tool runs in application code and the child-pattern exchange is not separately capturable | ➖ Not instrumentable |
