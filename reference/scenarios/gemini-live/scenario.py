"""Reference implementation for Google Gemini Live (voice-native) inference.

Exercises a speech-to-speech turn against the mock Gemini Live WebSocket server.
The user utterance and the model response form a single ``chat`` inference span
that carries the audio-modality messages and, crucially, the audio token usage
(``gen_ai.usage.audio.input_tokens`` / ``gen_ai.usage.audio.output_tokens``)
alongside the transcript of the spoken audio.

This proves that audio token usage and the audio transcript on a realtime
(Gemini Live) inference call are capturable by generic instrumentation of
``client.aio.live.connect``. It is the second provider (after OpenAI Realtime)
demonstrating the same convention against a differently-shaped bidi protocol.
Agent-level modeling (the ``invoke_agent`` turn container) is intentionally out
of scope for this inference-focused reference and is covered separately.
"""

import asyncio
import base64
import json
import os
import ssl

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()

# Tiny base64 stand-in for the PCM16 audio the user "speaks". The mock does not
# decode it; it only needs to be a valid base64 audio payload.
INPUT_AUDIO_B64 = "bW9jay11c2VyLWF1ZGlv"


def _gemini_live_base_url(http_base_url):
    """Derive the Gemini Live base URL from the HTTP mock base URL.

    The mock serves the Gemini Live WebSocket on the second port up from its
    HTTP endpoint (see the mock server). The Gemini client always upgrades the
    scheme to ``wss`` (TLS) itself, so an ``http`` base URL on that port is all
    it needs.
    """
    host, port = mock_server_host_port(http_base_url)
    return host, port + 2


def _audio_modality_tokens(details):
    """Return the token count for the AUDIO modality entry, if present."""
    if not details:
        return None
    for detail in details:
        if detail.modality is not None and str(detail.modality).endswith("AUDIO"):
            return detail.token_count
    return None


async def _run_inference(session, request_model, host, port):
    """Drive one Gemini Live voice turn and emit its chat inference span."""
    from google.genai import types

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
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
        # The live session produces speech output for this turn.
        "gen_ai.output.type": "speech",
    }
    if host:
        chat_attributes["server.address"] = host
    if port is not None:
        chat_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span(f"chat {request_model}", attributes=chat_attributes) as chat_span:
        chat_span.set_attribute("gen_ai.input.messages", input_messages)

        # The user speaks: stream their audio, then signal the end of the
        # utterance so the model responds.
        await session.send_realtime_input(
            audio=types.Blob(data=base64.b64decode(INPUT_AUDIO_B64), mime_type="audio/pcm")
        )
        await session.send_realtime_input(audio_stream_end=True)

        transcript_deltas = []
        audio_chunks = []
        response_model = None
        usage = None
        async for message in session.receive():
            server_content = message.server_content
            if server_content is not None:
                if server_content.output_transcription and server_content.output_transcription.text:
                    transcript_deltas.append(server_content.output_transcription.text)
                if server_content.model_turn and server_content.model_turn.parts:
                    for part in server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_chunks.append(part.inline_data.data)
            if message.usage_metadata is not None:
                usage = message.usage_metadata

        transcript = "".join(transcript_deltas)
        output_audio = base64.b64encode(b"".join(audio_chunks)).decode() if audio_chunks else ""
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
                "finish_reason": "stop",
            }
        ]
        if response_model:
            chat_span.set_attribute("gen_ai.response.model", response_model)
        chat_span.set_attribute("gen_ai.response.finish_reasons", ["stop"])
        chat_span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            if usage.prompt_token_count:
                chat_span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_token_count)
            if usage.response_token_count:
                chat_span.set_attribute("gen_ai.usage.output_tokens", usage.response_token_count)
            input_audio_tokens = _audio_modality_tokens(usage.prompt_tokens_details)
            if input_audio_tokens:
                chat_span.set_attribute("gen_ai.usage.audio.input_tokens", input_audio_tokens)
            output_audio_tokens = _audio_modality_tokens(usage.response_tokens_details)
            if output_audio_tokens:
                chat_span.set_attribute("gen_ai.usage.audio.output_tokens", output_audio_tokens)
        print(f"    -> {transcript[:60]}")


async def run_gemini_live_reference():
    """Scenario: a single Gemini Live voice-native inference turn."""
    from google import genai
    from google.genai import types

    print("  [gemini-live] voice-native inference (reference implementation)")
    request_model = "gemini-2.5-flash-native-audio-preview"
    host, live_port = _gemini_live_base_url(MOCK_BASE_URL)

    # The client forces the WebSocket scheme to wss (TLS); the mock serves TLS
    # with a self-signed cert, so connect with an unverified SSL context.
    unverified_ctx = ssl.create_default_context()
    unverified_ctx.check_hostname = False
    unverified_ctx.verify_mode = ssl.CERT_NONE

    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=f"http://{host}:{live_port}",
            api_version="v1beta",
            async_client_args={"ssl": unverified_ctx},
        ),
    )
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )
    async with client.aio.live.connect(model=request_model, config=config) as session:
        await _run_inference(session, request_model, host, live_port)


def main():
    print("=== Reference Implementation: Google Gemini Live (voice-native) Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_gemini_live_reference())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
