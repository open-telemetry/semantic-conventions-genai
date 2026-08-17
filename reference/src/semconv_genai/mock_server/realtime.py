"""Mock OpenAI Realtime (voice-native) WebSocket endpoint.

Speaks a deterministic subset of the OpenAI Realtime event protocol over a
WebSocket so reference scenarios can exercise turn-based, streaming voice
interactions -- including barge-in (interruption) -- against the real
``openai`` realtime client.

This runs as a standalone ``websockets`` asyncio server (started in a background
thread by the mock server) rather than a Flask endpoint, because the ``openai``
realtime client uses the ``websockets`` library and needs a fully compatible
server for permessage-deflate negotiation.

The scenario selects the per-turn behavior by setting
``response.metadata.mock_behavior`` on the ``response.create`` client event:

- ``complete``      -> the turn finishes normally (``response.done`` completed).
- ``function_call`` -> the generation emits a function-call output item and ends
  (``response.done`` completed); the scenario then runs the tool and asks for a
  second ``complete`` response. This is the sibling tool-call pattern.
- ``interrupted``   -> the user barges in mid-response; the server emits
  ``input_audio_buffer.speech_started`` and a cancelled ``response.done`` with
  ``status_details.reason == "turn_detected"``.

When the client commits the input audio buffer (``input_audio_buffer.commit``),
the server emits the user voice-activity events
(``input_audio_buffer.speech_started`` / ``input_audio_buffer.speech_stopped``)
that bracket the user's utterance, followed by ``input_audio_buffer.committed``.
"""

import asyncio
import itertools
import json
import threading

import websockets

_event_counter = itertools.count(1)


def _event_id():
    return f"event_mock_{next(_event_counter)}"


async def _send(ws, obj):
    await ws.send(json.dumps(obj))


def _usage():
    """Realtime usage with audio/text token breakdown for a voice-native turn."""
    return {
        "total_tokens": 70,
        "input_tokens": 42,
        "output_tokens": 28,
        "input_token_details": {"text_tokens": 17, "audio_tokens": 25},
        "output_token_details": {"text_tokens": 8, "audio_tokens": 20},
    }


async def _run_response(ws, behavior):
    response_id = "resp_mock_realtime_001"
    item_id = "item_mock_assistant_001"

    if behavior == "function_call":
        # The generation resolves to a tool call and then ends. The tool runs on
        # the client (sibling pattern); a subsequent response.create produces the
        # spoken answer.
        await _send(
            ws,
            {
                "type": "response.created",
                "event_id": _event_id(),
                "response": {"id": response_id, "object": "realtime.response", "status": "in_progress"},
            },
        )
        await _send(
            ws,
            {
                "type": "response.output_item.done",
                "event_id": _event_id(),
                "response_id": response_id,
                "output_index": 0,
                "item": {
                    "id": "item_mock_function_call_001",
                    "object": "realtime.item",
                    "type": "function_call",
                    "status": "completed",
                    "name": "get_weather",
                    "call_id": "call_mock_realtime_001",
                    "arguments": json.dumps({"location": "Seattle"}),
                },
            },
        )
        await _send(
            ws,
            {
                "type": "response.done",
                "event_id": _event_id(),
                "response": {
                    "id": response_id,
                    "object": "realtime.response",
                    "status": "completed",
                    "usage": _usage(),
                },
            },
        )
        return

    await _send(
        ws,
        {
            "type": "response.created",
            "event_id": _event_id(),
            "response": {"id": response_id, "object": "realtime.response", "status": "in_progress"},
        },
    )
    for delta in ["It is ", "sunny and ", "about 72 degrees "]:
        await _send(
            ws,
            {
                "type": "response.output_audio_transcript.delta",
                "event_id": _event_id(),
                "response_id": response_id,
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": delta,
            },
        )
    await _send(
        ws,
        {
            "type": "response.output_audio.delta",
            "event_id": _event_id(),
            "response_id": response_id,
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "delta": "bW9jay1hc3Npc3RhbnQtYXVkaW8=",
        },
    )

    if behavior == "interrupted":
        # Barge-in: new user speech is detected while the response is in flight,
        # so the server cancels the response. The transcript survives only as the
        # accumulated deltas above (no *.done transcript event fires).
        await _send(
            ws,
            {
                "type": "input_audio_buffer.speech_started",
                "event_id": _event_id(),
                "audio_start_ms": 640,
                "item_id": "item_mock_user_002",
            },
        )
        await _send(
            ws,
            {
                "type": "response.done",
                "event_id": _event_id(),
                "response": {
                    "id": response_id,
                    "object": "realtime.response",
                    "status": "cancelled",
                    "status_details": {"type": "cancelled", "reason": "turn_detected"},
                    "usage": _usage(),
                },
            },
        )
        return

    await _send(
        ws,
        {
            "type": "response.output_audio_transcript.done",
            "event_id": _event_id(),
            "response_id": response_id,
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "transcript": "It is sunny and about 72 degrees in Seattle.",
        },
    )
    await _send(
        ws,
        {
            "type": "response.done",
            "event_id": _event_id(),
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "status": "completed",
                "usage": _usage(),
            },
        },
    )


async def _emit_user_vad(ws):
    """Emit the server-side user voice-activity events bracketing an utterance."""
    user_item_id = f"item_mock_user_{next(_event_counter)}"
    await _send(
        ws,
        {
            "type": "input_audio_buffer.speech_started",
            "event_id": _event_id(),
            "audio_start_ms": 0,
            "item_id": user_item_id,
        },
    )
    await _send(
        ws,
        {
            "type": "input_audio_buffer.speech_stopped",
            "event_id": _event_id(),
            "audio_end_ms": 800,
            "item_id": user_item_id,
        },
    )
    await _send(
        ws,
        {
            "type": "input_audio_buffer.committed",
            "event_id": _event_id(),
            "item_id": user_item_id,
        },
    )


async def _handler(ws):
    await _send(
        ws,
        {
            "type": "session.created",
            "event_id": _event_id(),
            "session": {
                "type": "realtime",
                "id": "sess_mock_realtime_001",
                "model": "gpt-realtime",
                "output_modalities": ["audio"],
            },
        },
    )
    async for raw in ws:
        message = json.loads(raw)
        message_type = message.get("type")
        if message_type == "input_audio_buffer.commit":
            await _emit_user_vad(ws)
        elif message_type == "response.create":
            behavior = ((message.get("response") or {}).get("metadata") or {}).get("mock_behavior", "complete")
            await _run_response(ws, behavior)


async def _serve(host, port):
    async with websockets.serve(_handler, host, port):
        await asyncio.Future()


def start_in_thread(host, port):
    """Start the realtime WebSocket server in a daemon thread."""

    def _run():
        asyncio.run(_serve(host, port))

    thread = threading.Thread(target=_run, name="realtime-ws-server", daemon=True)
    thread.start()
    return thread
