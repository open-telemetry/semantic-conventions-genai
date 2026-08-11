"""Reference implementation for OpenAI Realtime (voice-native) inference.

Exercises a speech-to-speech turn against the mock realtime WebSocket server.
The user utterance and the model response form a single
``generate_live_content`` span that carries the audio-modality messages and,
crucially, the audio token usage (``gen_ai.usage.audio.input_tokens`` /
``gen_ai.usage.audio.output_tokens``).

A live session is long-lived and mostly idle, so it is not modeled as a span.
Instead the session is represented by the ``gen_ai.client.live_session.started``
and ``gen_ai.client.live_session.ended`` events, while ``gen_ai.conversation.id``
(the OpenAI realtime session id) correlates the generation to its session.

This proves that a realtime (``gpt-realtime``) server-side generation, its audio
token usage, and its session lifecycle are capturable by generic instrumentation
of ``client.realtime.connect``. Turn-level containers (a full user-and-model
exchange) are intentionally out of scope: turn boundaries cannot be detected
reliably across providers.
"""

import json
import os
import time

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


def _run_inference(conn, request_model, response_model, session_id, host, port):
    """Drive one realtime turn and emit its generate_live_content span."""
    input_messages = json.dumps(
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
    span_attributes = {
        "gen_ai.operation.name": "generate_live_content",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        # The realtime session produces speech output for this turn.
        "gen_ai.output.type": "speech",
    }
    if session_id:
        span_attributes["gen_ai.conversation.id"] = session_id
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span(
        f"generate_live_content {request_model}", attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)

        # The user speaks: append their audio to the input buffer, commit it,
        # then ask the model to respond.
        conn.send({"type": "input_audio_buffer.append", "audio": INPUT_AUDIO_B64})
        conn.send({"type": "input_audio_buffer.commit"})
        request_time = time.monotonic()
        conn.send({"type": "response.create", "response": {"metadata": {"mock_behavior": "complete"}}})

        response_id = None
        transcript_deltas = []
        audio_deltas = []
        final_transcript = None
        status = None
        usage = None
        time_to_first_chunk = None
        for event in conn:
            if event.type == "response.created":
                response_id = event.response.id
            elif event.type == "response.output_audio_transcript.delta":
                if time_to_first_chunk is None:
                    time_to_first_chunk = time.monotonic() - request_time
                transcript_deltas.append(event.delta)
            elif event.type == "response.output_audio.delta":
                if time_to_first_chunk is None:
                    time_to_first_chunk = time.monotonic() - request_time
                audio_deltas.append(event.delta)
            elif event.type == "response.output_audio_transcript.done":
                final_transcript = event.transcript
            elif event.type == "response.done":
                status = event.response.status
                usage = event.response.usage
                break

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
        span.set_attribute("gen_ai.response.model", response_model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if time_to_first_chunk is not None:
            span.set_attribute("gen_ai.response.time_to_first_chunk", time_to_first_chunk)
        span.set_attribute("gen_ai.response.finish_reasons", [status])
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            if usage.input_token_details and usage.input_token_details.audio_tokens:
                span.set_attribute("gen_ai.usage.audio.input_tokens", usage.input_token_details.audio_tokens)
            if usage.output_token_details and usage.output_token_details.audio_tokens:
                span.set_attribute("gen_ai.usage.audio.output_tokens", usage.output_token_details.audio_tokens)
        print(f"    -> {transcript[:60]}")


def run_realtime_reference(client):
    """Scenario: a single realtime voice-native inference turn within a live session."""
    print("  [realtime] voice-native inference (reference implementation)")
    request_model = "gpt-realtime"
    provider = "openai"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    with client.realtime.connect(model=request_model) as conn:
        session_event = conn.recv()  # session.created
        response_model = session_event.session.model or request_model
        session_id = session_event.session.id

        # The live session is established: record its start as an event,
        # correlated to the generation via conversation id.
        session_attributes = {
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": request_model,
        }
        if session_id:
            session_attributes["gen_ai.conversation.id"] = session_id
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
            _run_inference(conn, request_model, response_model, session_id, host, port)
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

