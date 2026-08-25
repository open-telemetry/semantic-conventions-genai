"""Reference implementation for OpenAI Realtime (voice-native) inference.

Exercises a live speech-to-speech session against the mock realtime WebSocket
server. The session emits ``gen_ai.client.live_session.started`` /
``gen_ai.client.live_session.ended`` events (a live session is long-lived and
mostly idle, so it is not modeled as a span) and ``gen_ai.live_session.id`` (the
OpenAI realtime session id) correlates everything within it.

Two turns run inside the one session:

1. A simple voice turn. The user's utterance is captured as a
   ``gen_ai.user_speech.internal`` span bounded by OpenAI Realtime's server
   voice-activity events -- the span starts at ``input_audio_buffer.speech_started``
   and ends at ``speech_stopped`` -- and the model response is a
   ``realtime_inference`` span carrying the audio-modality messages and audio
   token usage.
2. A tool-calling turn demonstrating the **sibling** tool-call pattern: the
   first ``realtime_inference`` span resolves to a function call and ends, an
   ``execute_tool`` span runs the tool, then a second ``realtime_inference``
   span speaks the answer. The tool span is a sibling of the two generations, so
   client-side tool runtime does not inflate model-generation latency.

Turn-level containers (a full user-and-model exchange) are intentionally out of
scope: turn boundaries cannot be detected reliably across providers.
"""

import json
import os

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
        attributes["gen_ai.live_session.id"] = session_id
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _capture_user_speech(conn, provider, session_id):
    """Bracket the user's utterance with a user_speech span delimited by server VAD.

    In server voice-activity-detection mode the client just streams audio; the
    server decides where the utterance starts and stops and emits
    ``input_audio_buffer.speech_started`` / ``speech_stopped``. Per the
    convention, the span starts at ``speech_started`` and ends at
    ``speech_stopped`` -- the server-detected speech boundaries -- rather than at
    the client's own append/commit calls (there is no manual commit here). Those
    server events are what a generic instrumentation observing the realtime event
    stream would key the span off.
    """
    # Stream the user's audio. With server VAD there is no manual commit; the
    # server detects the utterance boundaries from the audio it receives.
    conn.send({"type": "input_audio_buffer.append", "audio": INPUT_AUDIO_B64})

    span = None
    for event in conn:
        if event.type == "input_audio_buffer.speech_started":
            attributes = {
                "gen_ai.operation.name": "user_speech",
                "gen_ai.provider.name": provider,
            }
            if session_id:
                attributes["gen_ai.live_session.id"] = session_id
            span = _reference_tracer.start_span("user_speech", attributes=attributes)
        elif event.type == "input_audio_buffer.speech_stopped":
            # When a transcript of the user's audio is available it is carried here.
            span.set_attribute("gen_ai.input.messages", _user_audio_message())
            span.end()
            break


def _run_generation(conn, provider, request_model, response_model, session_id, host, port, behavior, input_messages):
    """Drive one server-side generation and emit its realtime_inference span.

    Returns the function call requested by the model, if any.
    """
    output_type = None if behavior == "function_call" else "speech"
    attributes = _live_attributes(
        provider, request_model, session_id, host, port, "realtime_inference", output_type=output_type
    )
    conn.send({"type": "response.create", "response": {"metadata": {"mock_behavior": behavior}}})
    with _reference_tracer.start_as_current_span(f"realtime_inference {request_model}", attributes=attributes) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)

        response_id = None
        transcript_deltas = []
        audio_deltas = []
        final_transcript = None
        status = None
        usage = None
        function_call = None
        for event in conn:
            if event.type == "response.created":
                response_id = event.response.id
            elif event.type == "response.output_audio_transcript.delta":
                transcript_deltas.append(event.delta)
            elif event.type == "response.output_audio.delta":
                audio_deltas.append(event.delta)
            elif event.type == "response.output_audio_transcript.done":
                final_transcript = event.transcript
            elif event.type == "response.output_item.done" and getattr(event.item, "type", None) == "function_call":
                function_call = {
                    "name": event.item.name,
                    "call_id": event.item.call_id,
                    "arguments": event.item.arguments,
                }
            elif event.type == "response.done":
                status = event.response.status
                usage = event.response.usage
                break

        span.set_attribute("gen_ai.response.model", response_model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)

        if function_call is not None:
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
        else:
            transcript = final_transcript if final_transcript is not None else "".join(transcript_deltas)
            output_audio = "".join(audio_deltas)
            output_messages = [
                {
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "blob",
                            "modality": "audio",
                            "mime_type": "audio/pcm",
                            "content": output_audio,
                            "transcript": transcript,
                        },
                    ],
                    "finish_reason": status,
                }
            ]
            span.set_attribute("gen_ai.response.finish_reasons", [status])
            print(f"    -> {transcript[:60]}")
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            if usage.input_token_details and usage.input_token_details.audio_tokens:
                span.set_attribute("gen_ai.usage.audio.input_tokens", usage.input_token_details.audio_tokens)
            if usage.output_token_details and usage.output_token_details.audio_tokens:
                span.set_attribute("gen_ai.usage.audio.output_tokens", usage.output_token_details.audio_tokens)
        return function_call


def _run_execute_tool(provider, function_call):
    """Run the requested tool and emit its execute_tool span (sibling of the generations)."""
    arguments = json.loads(function_call["arguments"])
    tool_attributes = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.provider.name": provider,
        "gen_ai.tool.name": function_call["name"],
        "gen_ai.tool.call.id": function_call["call_id"],
        "gen_ai.tool.type": "function",
    }
    with _reference_tracer.start_as_current_span(
        f"execute_tool {function_call['name']}", attributes=tool_attributes
    ) as span:
        span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
        result = {"location": arguments.get("location"), "temperature_f": 72, "conditions": "sunny"}
        span.set_attribute("gen_ai.tool.call.result", json.dumps(result))
    return result


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
                        "result": result,
                    }
                ],
            }
        ]
    )


def run_realtime_reference(client):
    """Scenario: two voice-native turns within a single live session."""
    print("  [realtime] voice-native inference (reference implementation)")
    request_model = "gpt-realtime"
    provider = "openai"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    with client.realtime.connect(model=request_model) as conn:
        session_event = conn.recv()  # session.created
        response_model = session_event.session.model or request_model
        session_id = session_event.session.id

        # The live session is established: record its start as an event,
        # correlated to the generations via live session id.
        session_attributes = {
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": request_model,
        }
        if session_id:
            session_attributes["gen_ai.live_session.id"] = session_id
        if host:
            session_attributes["server.address"] = host
        if port is not None:
            session_attributes["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.live_session.started",
            body="Live session started",
            attributes=session_attributes,
        )

        try:
            # Turn 1: a simple voice exchange -- user utterance then spoken answer.
            _capture_user_speech(conn, provider, session_id)
            _run_generation(
                conn,
                provider,
                request_model,
                response_model,
                session_id,
                host,
                port,
                behavior="complete",
                input_messages=_user_audio_message(),
            )

            # Turn 2: a tool-calling exchange (sibling pattern). The first
            # generation resolves to a function call, the tool runs as a sibling
            # span, then a second generation speaks the answer.
            _capture_user_speech(conn, provider, session_id)
            function_call = _run_generation(
                conn,
                provider,
                request_model,
                response_model,
                session_id,
                host,
                port,
                behavior="function_call",
                input_messages=_user_audio_message(),
            )
            result = _run_execute_tool(provider, function_call)
            conn.send(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": function_call["call_id"],
                        "output": json.dumps(result),
                    },
                }
            )
            _run_generation(
                conn,
                provider,
                request_model,
                response_model,
                session_id,
                host,
                port,
                behavior="complete",
                input_messages=_tool_result_message(function_call, result),
            )
        finally:
            # The session is closed: record its end as an event.
            reference_event_logger().emit(
                event_name="gen_ai.client.live_session.ended",
                body="Live session ended",
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
