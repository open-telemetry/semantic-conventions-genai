"""Reference implementation for OpenAI Realtime (voice-native) inference.

Exercises a realtime speech-to-speech session against the mock realtime WebSocket
server. The session emits ``gen_ai.client.realtime_session.started`` /
``gen_ai.client.realtime_session.ended`` events (a realtime session is long-lived and
mostly idle, so it is not modeled as a span) and ``gen_ai.realtime_session.id`` (the
OpenAI realtime session id) correlates everything within it.

All events are handled by a single continuous dispatch loop (see
``_RealtimeDriver``) that keeps independent user-speech and generation state, so
interleaved events are handled as they arrive rather than following a fixed
speech-then-generation sequence. Three turns run inside the one session:

1. A simple voice turn. The user's utterance is captured as a
   ``gen_ai.user_speech.internal`` span bounded by OpenAI Realtime's server
   voice-activity events -- the span starts at ``input_audio_buffer.speech_started``
   and ends at ``speech_stopped`` -- and the model response is a
   ``realtime_inference`` span carrying the audio-modality messages and audio
   token usage.
2. An interrupted (barge-in) turn. While the model is still streaming its
   response, the server detects new user speech (``input_audio_buffer.speech_started``
   arrives mid-response) and cancels the generation. Because speech and
   generation state are tracked independently, the barge-in opens its own
   ``user_speech`` span even though a generation span is still open; the
   cancelled generation ends with ``gen_ai.response.finish_reasons`` reflecting a
   stop, and the barge-in utterance is then answered by a follow-up generation.
3. A tool-calling turn demonstrating the **sibling** tool-call pattern: the
   first ``realtime_inference`` span resolves to a function call and ends, the
   client runs the tool, then a second ``realtime_inference`` span speaks the
   answer. Running the tool is application work, not a model operation, so it is
   not wrapped in a span; instead the model's request is captured as a
   ``tool_call`` output part on the first generation and the client's result as
   a ``tool_call_response`` input part on the answer generation.

Turn-level containers (a full user-and-model exchange) are intentionally out of
scope: turn boundaries cannot be detected reliably across providers.
"""

import json
import os
from collections import deque

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()

# Tiny base64 stand-in for the PCM16 audio the user "speaks". The mock does not
# decode it; it only needs to be a valid base64 audio payload.
INPUT_AUDIO_B64 = "bW9jay11c2VyLWF1ZGlv"


def _realtime_ws_url(http_base_url):
    """Derive the realtime WebSocket base URL from the HTTP mock base URL.

    The mock serves the realtime WebSocket on the next port up from its HTTP
    endpoint (see the mock server), so ``http://host:8080/v1`` maps to
    ``ws://host:8081/v1``.
    """
    host, port = mock_server_host_port(http_base_url)
    return f"ws://{host}:{port + 1}/v1"


def _user_audio_message():
    """The user's spoken input as an audio-modality input message."""
    return json.dumps(
        [
            {
                "role": "user",
                "parts": [
                    {
                        "type": "blob",
                        "modality": "audio",
                        "mime_type": "audio/pcm",
                        "content": INPUT_AUDIO_B64,
                    }
                ],
            }
        ]
    )


def _live_attributes(provider, request_model, session_id, host, port, operation, output_type=None):
    """Common attributes shared by the user_speech and realtime_inference spans."""
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": request_model,
    }
    if output_type:
        attributes["gen_ai.output.type"] = output_type
    if session_id:
        attributes["gen_ai.realtime_session.id"] = session_id
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


class _RealtimeDriver:
    """Continuous, event-driven dispatch for one realtime session.

    A single loop consumes provider events and keeps independent user-speech and
    generation state, so events that interleave -- most importantly a user
    barge-in (``input_audio_buffer.speech_started``) while a response is still
    streaming -- are handled as they arrive instead of being forced into a fixed
    speech-then-generation order. This mirrors how generic instrumentation
    observing the realtime event stream keys spans off the events themselves.

    The scenario only chooses *when the user speaks* and *what the mock should do*
    for each utterance (a normal answer, an interrupted answer, or a tool call);
    every span boundary is driven by the received events, not by the call order.
    """

    def __init__(self, conn, provider, request_model, response_model, session_id, host, port):
        self.conn = conn
        self.provider = provider
        self.request_model = request_model
        self.response_model = response_model
        self.session_id = session_id
        self.host = host
        self.port = port
        # What the mock should do for each committed user utterance, in order:
        # a normal answer, an interrupted answer, the interrupted turn's follow-up
        # answer, then a tool call.
        self._behaviors = deque(["complete", "interrupted", "complete", "function_call"])
        # User turns still to be started after a spoken answer completes.
        self._turns_remaining = 2
        self._speech_span = None
        self._gen = None
        self._function_call = None
        self._done = False

    def run(self):
        # The user speaks first; every span boundary after this is driven by the
        # received events.
        self._send_user_audio()
        for event in self.conn:
            self._dispatch(event)
            if self._done:
                break

    def _send_user_audio(self):
        # Streaming audio makes the server emit its own voice-activity events;
        # there is no manual commit in server-VAD mode.
        self.conn.send({"type": "input_audio_buffer.append", "audio": INPUT_AUDIO_B64})

    def _dispatch(self, event):
        handler = {
            "input_audio_buffer.speech_started": self._on_speech_started,
            "input_audio_buffer.speech_stopped": self._on_speech_stopped,
            "input_audio_buffer.committed": self._on_committed,
            "response.created": self._on_response_created,
            "response.output_audio_transcript.delta": self._on_transcript_delta,
            "response.output_audio.delta": self._on_audio_delta,
            "response.output_audio_transcript.done": self._on_transcript_done,
            "response.output_item.done": self._on_output_item_done,
            "response.done": self._on_response_done,
        }.get(event.type)
        if handler is not None:
            handler(event)

    def _on_speech_started(self, event):
        attributes = {
            "gen_ai.operation.name": "user_speech",
            "gen_ai.provider.name": self.provider,
        }
        if self.session_id:
            attributes["gen_ai.realtime_session.id"] = self.session_id
        # A speech_started received while a generation is still open is a
        # barge-in; the new utterance and the in-flight generation are tracked
        # independently.
        self._speech_span = _reference_tracer.start_span("user_speech", attributes=attributes)

    def _on_speech_stopped(self, event):
        # When a transcript of the user's audio is available it is carried here.
        self._speech_span.set_attribute("gen_ai.input.messages", _user_audio_message())
        self._speech_span.end()
        self._speech_span = None

    def _on_committed(self, event):
        # The user finished an utterance; ask the model to respond to it.
        self._start_generation(self._behaviors.popleft(), _user_audio_message())

    def _start_generation(self, behavior, input_messages):
        output_type = None if behavior == "function_call" else "speech"
        attributes = _live_attributes(
            self.provider,
            self.request_model,
            self.session_id,
            self.host,
            self.port,
            "realtime_inference",
            output_type=output_type,
        )
        span = _reference_tracer.start_span(f"realtime_inference {self.request_model}", attributes=attributes)
        span.set_attribute("gen_ai.input.messages", input_messages)
        self._gen = {
            "span": span,
            "response_id": None,
            "transcript_deltas": [],
            "audio_deltas": [],
            "final_transcript": None,
        }
        self.conn.send({"type": "response.create", "response": {"metadata": {"mock_behavior": behavior}}})

    def _on_response_created(self, event):
        self._gen["response_id"] = event.response.id

    def _on_transcript_delta(self, event):
        self._gen["transcript_deltas"].append(event.delta)

    def _on_audio_delta(self, event):
        self._gen["audio_deltas"].append(event.delta)

    def _on_transcript_done(self, event):
        self._gen["final_transcript"] = event.transcript

    def _on_output_item_done(self, event):
        if getattr(event.item, "type", None) == "function_call":
            self._function_call = {
                "name": event.item.name,
                "call_id": event.item.call_id,
                "arguments": event.item.arguments,
            }

    def _on_response_done(self, event):
        span = self._gen["span"]
        span.set_attribute("gen_ai.response.model", self.response_model)
        if self._gen["response_id"]:
            span.set_attribute("gen_ai.response.id", self._gen["response_id"])
        if self._function_call is not None:
            self._finish_tool_call_generation(span, event.response.usage)
        else:
            self._finish_spoken_generation(span, event.response.status, event.response.usage)

    def _finish_tool_call_generation(self, span, usage):
        function_call = self._function_call
        output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool_call",
                        "id": function_call["call_id"],
                        "name": function_call["name"],
                        "arguments": json.loads(function_call["arguments"]),
                    }
                ],
                "finish_reason": "tool_call",
            }
        ]
        span.set_attribute("gen_ai.response.finish_reasons", ["tool_call"])
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        self._set_usage(span, usage)
        span.end()
        self._gen = None
        self._function_call = None

        # The client runs the tool and returns the result; a follow-up generation
        # speaks the answer. The exchange is carried as message parts, not a span.
        result = _execute_tool(function_call)
        self.conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": function_call["call_id"],
                    "output": json.dumps(result),
                },
            }
        )
        self._start_generation("complete", _tool_result_message(function_call, result))

    def _finish_spoken_generation(self, span, status, usage):
        gen = self._gen
        transcript = (
            gen["final_transcript"] if gen["final_transcript"] is not None else "".join(gen["transcript_deltas"])
        )
        output_audio = "".join(gen["audio_deltas"])
        output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {"type": "blob", "modality": "audio", "mime_type": "audio/pcm", "content": output_audio},
                    {"type": "transcription", "content": transcript},
                ],
                "finish_reason": _finish_reason(status),
            }
        ]
        span.set_attribute("gen_ai.response.finish_reasons", [_finish_reason(status)])
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        self._set_usage(span, usage)
        span.end()
        self._gen = None
        print(f"    -> {transcript[:60]}")

        # A cancelled generation is an interruption: the barge-in utterance is
        # still in flight and is answered when it commits, so no new turn starts
        # here. Only a normal completion advances to the next user turn.
        if status == "completed":
            if self._turns_remaining > 0:
                self._turns_remaining -= 1
                self._send_user_audio()
            else:
                self._done = True

    @staticmethod
    def _set_usage(span, usage):
        if not usage:
            return
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        if usage.input_token_details and usage.input_token_details.audio_tokens is not None:
            span.set_attribute("gen_ai.usage.audio.input_tokens", usage.input_token_details.audio_tokens)
        if usage.output_token_details and usage.output_token_details.audio_tokens is not None:
            span.set_attribute("gen_ai.usage.audio.output_tokens", usage.output_token_details.audio_tokens)


# Realtime response ``status`` is a transport/lifecycle value; map it to a model
# stop reason for ``gen_ai.response.finish_reasons`` so emitted values match the
# semantic-convention definition rather than the raw protocol string.
_STATUS_TO_FINISH_REASON = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "stop",
}


def _finish_reason(status):
    return _STATUS_TO_FINISH_REASON.get(status, "stop")


def _execute_tool(function_call):
    """Run the requested tool on the client and return its result.

    In the realtime APIs the application executes tool calls and sends the
    result back to the model, so this client-side work is not itself a model
    operation and is not wrapped in a span. The request and result are captured
    as message parts on the generations instead: a ``tool_call`` output part on
    the requesting generation and a ``tool_call_response`` input part on the
    answer generation.
    """
    arguments = json.loads(function_call["arguments"])
    return {"location": arguments.get("location"), "temperature_f": 72, "conditions": "sunny"}


def _tool_result_message(function_call, result):
    """The tool result as the input message for the answer generation."""
    return json.dumps(
        [
            {
                "role": "tool",
                "parts": [
                    {
                        "type": "tool_call_response",
                        "id": function_call["call_id"],
                        "response": result,
                    }
                ],
            }
        ]
    )


def run_realtime_reference(client):
    """Scenario: two voice-native turns within a single realtime session."""
    print("  [realtime] voice-native inference (reference implementation)")
    request_model = "gpt-realtime"
    provider = "openai"
    host, http_port = mock_server_host_port(MOCK_BASE_URL)
    # The realtime inference runs over the WebSocket endpoint (health port + 1),
    # so server.port reflects the actual remote endpoint the requests reach.
    port = http_port + 1
    with client.realtime.connect(model=request_model) as conn:
        session_event = conn.recv()  # session.created
        response_model = session_event.session.model or request_model
        session_id = session_event.session.id

        # The realtime session is established: record its start as an event,
        # correlated to the generations via realtime session id.
        session_attributes = {
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": request_model,
        }
        if session_id:
            session_attributes["gen_ai.realtime_session.id"] = session_id
        if host:
            session_attributes["server.address"] = host
        if port is not None:
            session_attributes["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.realtime_session.started",
            body="Realtime session started",
            attributes=session_attributes,
        )

        try:
            _RealtimeDriver(
                conn,
                provider,
                request_model,
                response_model,
                session_id,
                host,
                port,
            ).run()
        finally:
            # The session is closed: record its end as an event.
            reference_event_logger().emit(
                event_name="gen_ai.client.realtime_session.ended",
                body="Realtime session ended",
                attributes=session_attributes,
            )


def main():
    print("=== Reference Implementation: OpenAI Realtime (voice-native) Reference Implementation ===")

    import openai

    tp, lp, mp = setup_otel()

    client = openai.OpenAI(
        base_url=MOCK_BASE_URL,
        websocket_base_url=_realtime_ws_url(MOCK_BASE_URL),
        api_key="mock-key",
    )
    run_realtime_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
