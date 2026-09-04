"""Reference implementation for Google Gemini Live (voice-native) inference.

Exercises two speech-to-speech turns within one live session against the mock
Gemini Live WebSocket server. Each server-side generation is a
``realtime_inference`` span that carries the audio-modality messages and,
crucially, the audio token usage (``gen_ai.usage.audio.input_tokens`` /
``gen_ai.usage.audio.output_tokens``) alongside the transcript of the spoken
audio.

The second turn exercises the sibling tool-call pattern: the first generation
resolves to a tool call, the tool runs as a sibling ``execute_tool`` span, and a
second generation speaks the answer. On Gemini Live the tool call surfaces as a
top-level ``toolCall`` message rather than nested inside the generation, so the
generation span closes before the tool runs and the answer is a separate
generation — the tool span is a sibling, not a child.

A live session is long-lived and mostly idle, so it is not modeled as a span.
Instead the session is represented by the ``gen_ai.client.live_session.started``
and ``gen_ai.client.live_session.ended`` events. The Gemini Developer API's
``setupComplete`` message has no fields, so it exposes no server session
identifier to the client and ``gen_ai.live_session.id`` is left unset here. When
a provider session id is not available, instrumentation may instead mint a
client-created per-connection id (the live connection is the session boundary)
and use it as ``gen_ai.live_session.id`` to correlate the session events with
the generations.

The Gemini Developer API also exposes no user voice-activity (VAD) events, so
there is no ``user_speech`` span here (another honest capture gap for this
provider); the user's spoken input is carried on the generation span through
``gen_ai.input.messages`` instead.

This proves that Gemini Live server-side generations, their audio token usage,
their audio transcripts, sibling tool calls, and their session lifecycle are
capturable by generic instrumentation of ``client.aio.live.connect``. It is the
second provider (after OpenAI Realtime) demonstrating the same convention
against a differently-shaped bidi protocol. Turn-level containers (a full
user-and-model exchange) are intentionally out of scope: turn boundaries cannot
be detected reliably across providers.
"""

import asyncio
import base64
import json
import os
import ssl

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
    """Derive the Gemini Live base URL from the HTTP mock base URL.

    The mock serves the Gemini Live WebSocket on the next port up from its
    HTTP (health) endpoint (see mock_server.py). The Gemini client always
    upgrades the scheme to ``wss`` (TLS) itself, so an ``http`` base URL on that
    port is all it needs.
    """
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


def _live_attributes(request_model, host, port, operation, output_type=None):
    """Common attributes shared by the realtime_inference spans."""
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
    }
    if output_type:
        attributes["gen_ai.output.type"] = output_type
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _tool_result_message(function_call, result):
    """The tool result as the input message for the answer generation."""
    return json.dumps(
        [
            {
                "role": "tool",
                "parts": [
                    {
                        "type": "tool_call_response",
                        "id": function_call["id"],
                        "result": result,
                    }
                ],
            }
        ]
    )


def _run_execute_tool(function_call):
    """Run the requested tool and emit its execute_tool span (sibling of the generations)."""
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
        result = {"location": function_call["args"].get("location"), "temperature_f": 72, "conditions": "sunny"}
        span.set_attribute("gen_ai.tool.call.result", json.dumps(result))
    return result


async def _run_generation(session, request_model, host, port, input_messages, break_on_tool_call):
    """Consume one server-side generation and emit its realtime_inference span.

    Returns the function call requested by the model, if any.
    """
    output_type = None if break_on_tool_call else "speech"
    attributes = _live_attributes(request_model, host, port, "realtime_inference", output_type=output_type)
    with _reference_tracer.start_as_current_span(f"realtime_inference {request_model}", attributes=attributes) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)

        transcript_deltas = []
        audio_chunks = []
        usage = None
        function_call = None
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
            if break_on_tool_call and message.tool_call is not None and message.tool_call.function_calls:
                call = message.tool_call.function_calls[0]
                function_call = {"id": call.id, "name": call.name, "args": dict(call.args or {})}
                break

        if function_call is not None:
            output_messages = [
                {
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool_call",
                            "id": function_call["id"],
                            "name": function_call["name"],
                            "arguments": function_call["args"],
                        }
                    ],
                    "finish_reason": "tool_call",
                }
            ]
            span.set_attribute("gen_ai.response.finish_reasons", ["tool_call"])
        else:
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
            span.set_attribute("gen_ai.response.finish_reasons", ["stop"])
            print(f"    -> {transcript[:60]}")
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
        return function_call


async def _send_user_audio(session):
    """Stream the user's audio and signal the end of the utterance."""
    from google.genai import types

    await session.send_realtime_input(audio=types.Blob(data=base64.b64decode(INPUT_AUDIO_B64), mime_type="audio/pcm"))
    await session.send_realtime_input(audio_stream_end=True)


async def run_gemini_live_reference():
    """Scenario: two Gemini Live voice-native turns within a single live session."""
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
        # The live session is established: record its start as an event. Gemini
        # Live exposes no session id, so gen_ai.live_session.id is left unset.
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
            # Turn 1: a simple voice exchange. The Gemini Developer API exposes no
            # user voice-activity events, so there is no user_speech span (an honest
            # capture gap for this provider); the user input is carried on the
            # generation span through gen_ai.input.messages instead.
            await _send_user_audio(session)
            await _run_generation(
                session, request_model, host, live_port, _user_audio_message(), break_on_tool_call=False
            )

            # Turn 2: a tool-calling exchange (sibling pattern, Gemini Live 2.5).
            # The first generation resolves to a tool call, the tool runs as a
            # sibling span, then a second generation speaks the answer.
            await _send_user_audio(session)
            function_call = await _run_generation(
                session, request_model, host, live_port, _user_audio_message(), break_on_tool_call=True
            )
            result = _run_execute_tool(function_call)
            await session.send_tool_response(
                function_responses=[
                    types.FunctionResponse(id=function_call["id"], name=function_call["name"], response=result)
                ]
            )
            await _run_generation(
                session,
                request_model,
                host,
                live_port,
                _tool_result_message(function_call, result),
                break_on_tool_call=False,
            )
        finally:
            # The session is closed: record its end as an event.
            reference_event_logger().emit(
                event_name="gen_ai.client.live_session.ended",
                body="Live session ended",
                attributes=session_attributes,
            )


def main():
    print("=== Reference Implementation: Google Gemini Live (voice-native) Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_gemini_live_reference())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
