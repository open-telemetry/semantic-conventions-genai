"""Reference implementation for a cascade (STT -> LLM -> TTS) voice agent.

A cascade voice pipeline handles a spoken turn in three stages using separate
models: speech-to-text (transcription), a text LLM, and text-to-speech
(synthesis). This scenario drives all three against the mock server under a
single `invoke_agent` container span to prove the pipeline is capturable by
generic instrumentation of the OpenAI audio + chat APIs:

- `speech_to_text` span -> `gen_ai.speech.input.language` + transcript.
- `chat` span -> the text LLM turn (reuses the existing inference convention).
- `text_to_speech` span -> `gen_ai.speech.voice` + synthesized audio output.
"""

import base64
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

# Tiny stand-in for the PCM/WAV bytes the user "speaks". The mock does not
# decode it; it only needs to round-trip through the SDK as an upload.
INPUT_AUDIO_BYTES = b"mock-user-utterance-audio"


def _server_attributes(host, port):
    attributes = {}
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def run_cascade_reference(client):
    """Scenario: a cascade voice pipeline turn (STT -> LLM -> TTS)."""
    print("  [cascade] STT -> LLM -> TTS voice pipeline (reference implementation)")
    host, port = mock_server_host_port(MOCK_BASE_URL)

    stt_model = "whisper-1"
    stt_language = "en"
    llm_model = "gpt-4o"
    tts_model = "gpt-4o-mini-tts"
    tts_voice = "alloy"

    agent_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.agent.name": "voice-assistant",
        **_server_attributes(host, port),
    }
    with _reference_tracer.start_as_current_span("invoke_agent voice-assistant", attributes=agent_attributes):
        # --- Stage 1: speech-to-text (transcription) ---
        stt_attributes = {
            "gen_ai.operation.name": "speech_to_text",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": stt_model,
            **_server_attributes(host, port),
        }
        with _reference_tracer.start_as_current_span(
            f"speech_to_text {stt_model}", attributes=stt_attributes
        ) as stt_span:
            stt_span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "type": "blob",
                                    "modality": "audio",
                                    "mime_type": "audio/wav",
                                    "content": base64.b64encode(INPUT_AUDIO_BYTES).decode(),
                                }
                            ],
                        }
                    ]
                ),
            )
            transcription = client.audio.transcriptions.create(
                model=stt_model,
                file=("speech.wav", INPUT_AUDIO_BYTES, "audio/wav"),
                language=stt_language,
                response_format="verbose_json",
            )
            transcript = transcription.text
            stt_span.set_attribute("gen_ai.response.model", stt_model)
            # The transcription reports the language it detected (or the one
            # declared in the request); record it as the input audio language.
            if transcription.language:
                stt_span.set_attribute("gen_ai.speech.input.language", transcription.language)
            stt_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [{"role": "assistant", "parts": [{"type": "text", "content": transcript}], "finish_reason": "stop"}]
                ),
            )
            print(f"    [stt] ({transcription.language}) -> {transcript}")

        # --- Stage 2: text LLM inference ---
        chat_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": llm_model,
            "gen_ai.output.type": "text",
            **_server_attributes(host, port),
        }
        with _reference_tracer.start_as_current_span(f"chat {llm_model}", attributes=chat_attributes) as chat_span:
            chat_span.set_attribute(
                "gen_ai.input.messages",
                json.dumps([{"role": "user", "parts": [{"type": "text", "content": transcript}]}]),
            )
            completion = client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": transcript}],
            )
            choice = completion.choices[0]
            llm_text = choice.message.content
            chat_span.set_attribute("gen_ai.response.model", completion.model)
            chat_span.set_attribute("gen_ai.response.id", completion.id)
            chat_span.set_attribute("gen_ai.response.finish_reasons", [choice.finish_reason])
            chat_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": choice.message.role,
                            "parts": [{"type": "text", "content": llm_text}],
                            "finish_reason": choice.finish_reason,
                        }
                    ]
                ),
            )
            usage = completion.usage
            if usage:
                chat_span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
                chat_span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
            print(f"    [llm] -> {llm_text}")

        # --- Stage 3: text-to-speech (synthesis) ---
        tts_attributes = {
            "gen_ai.operation.name": "text_to_speech",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": tts_model,
            # The pipeline requests speech output for this synthesis stage.
            "gen_ai.output.type": "speech",
            "gen_ai.speech.voice": tts_voice,
            **_server_attributes(host, port),
        }
        with _reference_tracer.start_as_current_span(
            f"text_to_speech {tts_model}", attributes=tts_attributes
        ) as tts_span:
            tts_span.set_attribute(
                "gen_ai.input.messages",
                json.dumps([{"role": "user", "parts": [{"type": "text", "content": llm_text}]}]),
            )
            speech = client.audio.speech.create(model=tts_model, voice=tts_voice, input=llm_text)
            output_audio = base64.b64encode(speech.content).decode()
            tts_span.set_attribute("gen_ai.response.model", tts_model)
            tts_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [
                                {
                                    "type": "blob",
                                    "modality": "audio",
                                    "mime_type": "audio/mpeg",
                                    "content": output_audio,
                                }
                            ],
                        }
                    ]
                ),
            )
            print(f"    [tts] voice={tts_voice} -> {len(speech.content)} bytes of audio")


def main():
    print("=== Reference Implementation: OpenAI Cascade (STT -> LLM -> TTS) Voice Pipeline ===")

    import openai

    tp, lp, mp = setup_otel()

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    run_cascade_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
