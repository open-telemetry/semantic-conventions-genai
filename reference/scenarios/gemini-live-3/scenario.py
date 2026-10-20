"""Reference implementation for Google Gemini Live 3.x voice inference.

The mock server reports the tool request and the spoken answer within one
generation. The ``realtime_inference`` span remains open until the provider
reports generation or turn completion.

The SDK exposes the tool request through ``session.receive`` and accepts the
result through ``session.send_tool_response``. Instrumentation records both as
``tool_call`` and ``tool_call_response`` message parts. The application executes
the tool, so this client scenario does not emit an ``execute_tool`` span.

The session is represented by ``gen_ai.client.realtime_session.started`` and
``gen_ai.client.realtime_session.ended`` events. The Gemini Developer API's
``setupComplete`` message contains no server session identifier, so
``gen_ai.realtime_session.id`` is unset.

The Gemini Developer API also exposes no user voice-activity events, so this
scenario does not emit a ``user_speech`` span. The user's audio is recorded in
``gen_ai.input.messages`` on the generation span.
"""

import asyncio
import base64
import json
import os
import ssl

from opentelemetry import context as otel_context
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import SpanKind

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
    return host, port + 1


def _audio_modality_tokens(details):
    """Return the token count for the AUDIO modality entry, if present."""
    if not details:
        return None
    for detail in details:
        if detail.modality is not None and str(detail.modality).endswith("AUDIO"):
            return detail.token_count
    return None


def _user_audio_message():
    """Return the user's spoken input as an audio message."""
    return {
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


def _tool_call_message(function_call):
    """Return the model's tool request as an assistant message."""
    return {
        "role": "assistant",
        "parts": [
            {
                "type": "tool_call",
                "id": function_call["id"],
                "name": function_call["name"],
                "arguments": function_call["args"],
            }
        ],
    }


def _tool_response_message(function_call, result):
    """Return the application's tool result as a tool message."""
    return {
        "role": "tool",
        "parts": [
            {
                "type": "tool_call_response",
                "id": function_call["id"],
                "response": result,
            }
        ],
    }


def _execute_tool(function_call):
    """Run the requested tool in the application and return its result.

    In the Gemini Live API the application executes tool calls and sends the
    result back to the model. The client instrumentation does not own this
    operation and does not emit an ``execute_tool`` span.
    """
    return {
        "location": function_call["args"].get("location"),
        "temperature_f": 72,
        "conditions": "sunny",
    }


async def _run_generation(session, request_model, host, port):
    """Drive one voice turn with a tool exchange within one generation."""
    from google.genai import types

    span_attributes = {
        "gen_ai.operation.name": "realtime_inference",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
        "gen_ai.output.type": "speech",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port

    # The user speaks: stream their audio, then signal the end of the utterance.
    await session.send_realtime_input(audio=types.Blob(data=base64.b64decode(INPUT_AUDIO_B64), mime_type="audio/pcm"))
    await session.send_realtime_input(audio_stream_end=True)

    caller_context = otel_context.get_current()
    with _reference_tracer.start_as_current_span(
        f"realtime_inference {request_model}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        input_messages = [_user_audio_message()]
        span.set_attribute("gen_ai.input.messages", json.dumps(input_messages))

        transcript_deltas = []
        audio_chunks = []
        usage = None

        # First leg of the generation: the model requests a tool call.
        function_call = None
        async for message in session.receive():
            if message.tool_call is not None and message.tool_call.function_calls:
                call = message.tool_call.function_calls[0]
                function_call = {"id": call.id, "name": call.name, "args": dict(call.args or {})}
                break
            if message.usage_metadata is not None:
                usage = message.usage_metadata

        # The generation span remains open, but application tool execution uses
        # the caller's context rather than inheriting the client span.
        context_token = otel_context.attach(caller_context)
        try:
            result = _execute_tool(function_call)
            input_messages.append(_tool_response_message(function_call, result))
        finally:
            otel_context.detach(context_token)
        span.set_attribute("gen_ai.input.messages", json.dumps(input_messages))
        await session.send_tool_response(
            function_responses=[
                types.FunctionResponse(id=function_call["id"], name=function_call["name"], response=result)
            ]
        )

        # Second leg of the same generation: the model speaks its answer.
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
            _tool_call_message(function_call),
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "blob",
                        "modality": "audio",
                        "mime_type": "audio/pcm",
                        "content": output_audio,
                    },
                    {
                        "type": "transcription",
                        "content": transcript,
                    },
                ],
                "finish_reason": "stop",
            }
        ]
        span.set_attribute("gen_ai.response.finish_reasons", ["stop"])
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if usage:
            if usage.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_token_count)
            if usage.response_token_count:
                span.set_attribute("gen_ai.usage.output_tokens", usage.response_token_count)
            input_audio_tokens = _audio_modality_tokens(usage.prompt_tokens_details)
            if input_audio_tokens is not None:
                span.set_attribute("gen_ai.usage.audio.input_tokens", input_audio_tokens)
            output_audio_tokens = _audio_modality_tokens(usage.response_tokens_details)
            if output_audio_tokens is not None:
                span.set_attribute("gen_ai.usage.audio.output_tokens", output_audio_tokens)
        print(f"    -> {transcript[:60]}")


async def run_gemini_live_3_reference():
    """Run a Gemini Live 3.x tool exchange within one generation."""
    from google import genai
    from google.genai import types

    print("  [gemini-live-3] voice inference with a tool exchange in one generation")
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
            event_name="gen_ai.client.realtime_session.started",
            severity_number=SeverityNumber.INFO,
            body="Realtime session started",
            attributes=session_attributes,
        )
        try:
            await _run_generation(session, request_model, host, live_port)
        finally:
            reference_event_logger().emit(
                event_name="gen_ai.client.realtime_session.ended",
                severity_number=SeverityNumber.INFO,
                body="Realtime session ended",
                attributes=session_attributes,
            )


def main():
    print("=== Reference Implementation: Google Gemini Live 3.x (voice-native) Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_gemini_live_3_reference())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
