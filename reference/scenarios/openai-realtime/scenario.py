"""Reference implementation for OpenAI Realtime (voice-native) inference.

Exercises a speech-to-speech turn against the mock realtime WebSocket server.
The user utterance and the model response form a single ``chat`` inference span
that carries the audio-modality messages and, crucially, the audio token usage
(``gen_ai.usage.audio.input_tokens`` / ``gen_ai.usage.audio.output_tokens``).

This proves that audio token usage on a realtime (``gpt-realtime``) inference
call is capturable by generic instrumentation of ``client.realtime.connect``.
Agent-level modeling (the ``invoke_agent`` turn container, interruption /
barge-in outcomes) is intentionally out of scope for this inference-focused
reference and is covered separately.
"""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
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


def _run_inference(conn, request_model, response_model, host, port):
    """Drive one realtime turn and emit its chat inference span."""
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
    chat_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        # The realtime session produces speech output for this turn.
        "gen_ai.output.type": "speech",
    }
    if host:
        chat_attributes["server.address"] = host
    if port is not None:
        chat_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span(f"chat {request_model}", attributes=chat_attributes) as chat_span:
        chat_span.set_attribute("gen_ai.input.messages", input_messages)

        # The user speaks: append their audio to the input buffer, commit it,
        # then ask the model to respond.
        conn.send({"type": "input_audio_buffer.append", "audio": INPUT_AUDIO_B64})
        conn.send({"type": "input_audio_buffer.commit"})
        conn.send({"type": "response.create", "response": {"metadata": {"mock_behavior": "complete"}}})

        response_id = None
        transcript_deltas = []
        audio_deltas = []
        final_transcript = None
        status = None
        usage = None
        for event in conn:
            if event.type == "response.created":
                response_id = event.response.id
            elif event.type == "response.output_audio_transcript.delta":
                transcript_deltas.append(event.delta)
            elif event.type == "response.output_audio.delta":
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
        chat_span.set_attribute("gen_ai.response.model", response_model)
        if response_id:
            chat_span.set_attribute("gen_ai.response.id", response_id)
        chat_span.set_attribute("gen_ai.response.finish_reasons", [status])
        chat_span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            chat_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            chat_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            if usage.input_token_details and usage.input_token_details.audio_tokens:
                chat_span.set_attribute("gen_ai.usage.audio.input_tokens", usage.input_token_details.audio_tokens)
            if usage.output_token_details and usage.output_token_details.audio_tokens:
                chat_span.set_attribute("gen_ai.usage.audio.output_tokens", usage.output_token_details.audio_tokens)
        print(f"    -> {transcript[:60]}")


def run_realtime_reference(client):
    """Scenario: a single realtime voice-native inference turn."""
    print("  [realtime] voice-native inference (reference implementation)")
    request_model = "gpt-realtime"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    with client.realtime.connect(model=request_model) as conn:
        session_event = conn.recv()  # session.created
        response_model = session_event.session.model or request_model
        _run_inference(conn, request_model, response_model, host, port)


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
