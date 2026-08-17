"""Reference implementation for Google Gemini Live 3.x (voice-native) inference.

Exercises the *child* tool-call pattern within one live session against the mock
Gemini Live WebSocket server. Unlike Gemini Live 2.5 (see the ``gemini-live``
scenario, sibling pattern), a Gemini Live 3.x tool call is resolved *within* a
single generation: the model asks for a tool, the client runs it and returns the
result, and the *same* generation then speaks its answer. The
``generate_live_content`` span therefore stays open across the tool call and the
``execute_tool`` span is nested as its child.

A live session is long-lived and mostly idle, so it is not modeled as a span.
Instead the session is represented by the ``gen_ai.client.live_session.started``
and ``gen_ai.client.live_session.ended`` events. Gemini Live does not expose a
session identifier to the client, so ``gen_ai.conversation.id`` is left unset
here (an honest capture gap for this provider).

The Gemini Developer API also exposes no user voice-activity (VAD) events, so
there is no ``user_input`` span here (another honest capture gap for this
provider); the user's spoken input is carried on the generation span through
``gen_ai.input.messages`` instead.

This proves that the child tool-call pattern is capturable by generic
instrumentation of ``client.aio.live.connect`` and complements the sibling
pattern demonstrated by the ``openai-realtime`` and ``gemini-live`` scenarios.
"""

import asyncio
import base64
import json
import os
import ssl
import time

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()

# Tiny base64 stand-in for the PCM16 audio the user "speaks". The mock does not
# decode it; it only needs to be a valid base64 audio payload.
INPUT_AUDIO_B64 = "bW9jay11c2VyLWF1ZGlv"


def _gemini_live_base_url(http_base_url):
    """Derive the Gemini Live base URL from the HTTP mock base URL."""
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


def _run_execute_tool(function_call):
    """Run the requested tool and emit its execute_tool span (child of the generation)."""
    tool_attributes = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.tool.name": function_call["name"],
        "gen_ai.tool.call.id": function_call["id"],
        "gen_ai.tool.type": "function",
    }
    with _reference_tracer.start_as_current_span(
        f"execute_tool {function_call['name']}", attributes=tool_attributes
    ) as span:
        span.set_attribute("gen_ai.tool.call.arguments", json.dumps(function_call["args"]))
        result = {
            "location": function_call["args"].get("location"),
            "temperature_f": 72,
            "conditions": "sunny",
        }
        span.set_attribute("gen_ai.tool.call.result", json.dumps(result))
    return result


async def _run_generation(session, request_model, host, port):
    """Drive one Gemini Live 3.x voice turn where a tool call is a child of the generation."""
    from google.genai import types

    span_attributes = {
        "gen_ai.operation.name": "generate_live_content",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
        "gen_ai.output.type": "speech",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span(
        f"generate_live_content {request_model}", attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.input.messages", _user_audio_message())

        # The user speaks: stream their audio, then signal the end of the utterance.
        await session.send_realtime_input(
            audio=types.Blob(data=base64.b64decode(INPUT_AUDIO_B64), mime_type="audio/pcm")
        )
        request_time = time.monotonic()
        await session.send_realtime_input(audio_stream_end=True)

        transcript_deltas = []
        audio_chunks = []
        usage = None
        time_to_first_chunk = None

        # First leg of the generation: the model requests a tool call.
        function_call = None
        async for message in session.receive():
            if message.tool_call is not None and message.tool_call.function_calls:
                call = message.tool_call.function_calls[0]
                function_call = {"id": call.id, "name": call.name, "args": dict(call.args or {})}
                break
            if message.usage_metadata is not None:
                usage = message.usage_metadata

        # The tool runs as a child of this still-open generation span.
        result = _run_execute_tool(function_call)
        await session.send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id=function_call["id"], name=function_call["name"], response=result
                )
            ]
        )

        # Second leg of the same generation: the model speaks its answer.
        async for message in session.receive():
            server_content = message.server_content
            if server_content is not None:
                if server_content.output_transcription and server_content.output_transcription.text:
                    if time_to_first_chunk is None:
                        time_to_first_chunk = time.monotonic() - request_time
                    transcript_deltas.append(server_content.output_transcription.text)
                if server_content.model_turn and server_content.model_turn.parts:
                    for part in server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            if time_to_first_chunk is None:
                                time_to_first_chunk = time.monotonic() - request_time
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
        if time_to_first_chunk is not None:
            span.set_attribute("gen_ai.response.time_to_first_chunk", time_to_first_chunk)
        span.set_attribute("gen_ai.response.finish_reasons", ["stop"])
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            if usage.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_token_count)
            if usage.response_token_count:
                span.set_attribute("gen_ai.usage.output_tokens", usage.response_token_count)
            input_audio_tokens = _audio_modality_tokens(usage.prompt_tokens_details)
            if input_audio_tokens:
                span.set_attribute("gen_ai.usage.audio.input_tokens", input_audio_tokens)
            output_audio_tokens = _audio_modality_tokens(usage.response_tokens_details)
            if output_audio_tokens:
                span.set_attribute("gen_ai.usage.audio.output_tokens", output_audio_tokens)
        print(f"    -> {transcript[:60]}")


async def run_gemini_live_3_reference():
    """Scenario: a Gemini Live 3.x voice turn with a child-pattern tool call."""
    from google import genai
    from google.genai import types

    print("  [gemini-live-3] voice-native inference with child tool call (reference implementation)")
    request_model = "gemini-3-flash-native-audio-preview"
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
        session_attributes = {
            "gen_ai.provider.name": "gcp.gemini",
            "gen_ai.request.model": request_model,
        }
        if host:
            session_attributes["server.address"] = host
        if live_port is not None:
            session_attributes["server.port"] = live_port
        reference_event_logger().emit(
            event_name="gen_ai.client.live_session.started",
            body="Live session started",
            attributes=session_attributes,
        )
        try:
            await _run_generation(session, request_model, host, live_port)
        finally:
            reference_event_logger().emit(
                event_name="gen_ai.client.live_session.ended",
                body="Live session ended",
                attributes=session_attributes,
            )


def main():
    print("=== Reference Implementation: Google Gemini Live 3.x (voice-native) Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_gemini_live_3_reference())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
