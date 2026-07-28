"""Mock Google Gemini Live (bidirectional voice) WebSocket endpoint.

Speaks a deterministic subset of the Gemini Live ``BidiGenerateContent``
protocol over a secure WebSocket so reference scenarios can exercise
turn-based, streaming voice interactions against the real ``google-genai``
live client (``client.aio.live.connect``).

This runs as a standalone ``websockets`` asyncio server (started in a background
thread by the mock server) rather than a Flask endpoint, because the
``google-genai`` live client uses the ``websockets`` library over its own bidi
framing. The client always upgrades the connection to ``wss`` (TLS) regardless
of the configured base URL, so this server terminates TLS using a checked-in
self-signed certificate. The scenario connects with an unverified SSL context,
so the certificate's contents and hostname are irrelevant.

Server -> client turn sequence for one voice response:

1. ``{"serverContent": {"outputTranscription": {"text": ...}}}`` deltas -- the
   spoken audio transcript, streamed incrementally.
2. ``{"serverContent": {"modelTurn": {"parts": [{"inlineData": ...}]}}}`` -- the
   generated audio (PCM) for the turn.
3. ``{"serverContent": {"generationComplete": true}}``.
4. ``{"serverContent": {"turnComplete": true}, "usageMetadata": {...}}`` -- ends
   the turn and reports token usage with an ``AUDIO`` / ``TEXT`` modality
   breakdown for both prompt and response.
"""

import asyncio
import json
import ssl
import threading
from pathlib import Path

import websockets

_CERT_FILE = Path(__file__).with_name("gemini_live_cert.pem")
_KEY_FILE = Path(__file__).with_name("gemini_live_key.pem")

# Deterministic base64 stand-in for the PCM audio the model "speaks". The client
# decodes it to bytes; the scenario re-encodes it for the output message.
OUTPUT_AUDIO_B64 = "bW9jay1nZW1pbmktYXVkaW8="

TRANSCRIPT_DELTAS = ["It is ", "sunny and ", "about 72 degrees ", "in Seattle."]


async def _send(ws, obj):
    await ws.send(json.dumps(obj))


def _usage():
    """Live usage with an AUDIO/TEXT modality breakdown for a voice turn."""
    return {
        "promptTokenCount": 42,
        "responseTokenCount": 28,
        "totalTokenCount": 70,
        "promptTokensDetails": [
            {"modality": "AUDIO", "tokenCount": 25},
            {"modality": "TEXT", "tokenCount": 17},
        ],
        "responseTokensDetails": [
            {"modality": "AUDIO", "tokenCount": 20},
            {"modality": "TEXT", "tokenCount": 8},
        ],
    }


async def _run_turn(ws):
    for delta in TRANSCRIPT_DELTAS:
        await _send(ws, {"serverContent": {"outputTranscription": {"text": delta}}})
    await _send(
        ws,
        {
            "serverContent": {
                "modelTurn": {
                    "role": "model",
                    "parts": [{"inlineData": {"mimeType": "audio/pcm", "data": OUTPUT_AUDIO_B64}}],
                }
            }
        },
    )
    await _send(ws, {"serverContent": {"generationComplete": True}})
    await _send(ws, {"serverContent": {"turnComplete": True}, "usageMetadata": _usage()})


async def _handler(ws):
    async for raw in ws:
        message = json.loads(raw)
        if "setup" in message:
            await _send(ws, {"setupComplete": {}})
        elif "realtime_input" in message:
            realtime_input = message["realtime_input"] or {}
            # The client signals the end of the user's utterance; the model then
            # generates its spoken response for the accumulated audio.
            if realtime_input.get("audioStreamEnd"):
                await _run_turn(ws)


async def _serve(host, port):
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=_CERT_FILE, keyfile=_KEY_FILE)
    async with websockets.serve(_handler, host, port, ssl=ssl_ctx):
        await asyncio.Future()


def start_in_thread(host, port):
    """Start the Gemini Live WebSocket server in a daemon thread."""

    def _run():
        asyncio.run(_serve(host, port))

    thread = threading.Thread(target=_run, name="gemini-live-ws-server", daemon=True)
    thread.start()
    return thread
