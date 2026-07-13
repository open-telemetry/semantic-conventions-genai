"""Reference implementation for OpenAI voice-native (audio) chat completions.

Exercises a speech-to-speech turn against the mock server: the user sends
audio input and the model returns audio output plus a transcript. This proves
that audio token usage (`gen_ai.usage.input_audio_tokens` /
`gen_ai.usage.output_audio_tokens`) and audio-modality messages are capturable
by generic instrumentation of `client.chat.completions.create`.
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

# Tiny base64 stand-in for PCM/WAV audio bytes. The mock does not decode it;
# it only needs to be a valid base64 audio payload the SDK will round-trip.
INPUT_AUDIO_B64 = "bW9jay11c2VyLWF1ZGlv"


def run_audio_chat_reference(client):
    """Scenario: voice-native chat completion (audio in, audio out)."""
    print("  [audio-chat] voice-native chat completion (reference implementation)")
    request_model = "gpt-4o-audio-preview"
    request_voice = "alloy"
    request_audio_format = "wav"
    system_text = "You are a helpful voice assistant."
    messages = [
        {"role": "system", "content": system_text},
        {
            "role": "user",
            "content": [
                {"type": "input_audio", "input_audio": {"data": INPUT_AUDIO_B64, "format": request_audio_format}},
            ],
        },
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    input_messages = json.dumps(
        [
            {"role": "system", "parts": [{"type": "text", "content": system_text}]},
            {
                "role": "user",
                "parts": [
                    {
                        "type": "blob",
                        "modality": "audio",
                        "mime_type": "audio/wav",
                        "content": INPUT_AUDIO_B64,
                    }
                ],
            },
        ]
    )
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        # The client requests speech output for this voice-native turn.
        "gen_ai.output.type": "speech",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "chat gpt-4o-audio-preview", attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.chat.completions.create(
            model=request_model,
            modalities=["text", "audio"],
            audio={"voice": request_voice, "format": request_audio_format},
            messages=messages,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])

        choice = resp.choices[0]
        audio = choice.message.audio
        output_messages = [
            {
                "role": choice.message.role,
                "parts": [
                    {
                        "type": "blob",
                        "modality": "audio",
                        "mime_type": "audio/wav",
                        "content": audio.data,
                    },
                    {"type": "text", "content": audio.transcript},
                ],
                "finish_reason": choice.finish_reason,
            }
        ]
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))

        usage = resp.usage
        if usage:
            span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
            input_details = usage.prompt_tokens_details
            if input_details and input_details.audio_tokens:
                span.set_attribute("gen_ai.usage.input_audio_tokens", input_details.audio_tokens)
            output_details = usage.completion_tokens_details
            if output_details and output_details.audio_tokens:
                span.set_attribute("gen_ai.usage.output_audio_tokens", output_details.audio_tokens)
        print(f"    -> {audio.transcript[:60]}")


def main():
    print("=== Reference Implementation: OpenAI Audio (voice-native) Reference Implementation ===")

    import openai

    tp, lp, mp = setup_otel()

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    run_audio_chat_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
