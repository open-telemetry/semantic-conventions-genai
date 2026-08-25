"""Self-contained mock server for the Gemini Live reference scenario.

The conformance runner starts this via ``conformance.yaml``'s ``server.run``,
telling it which port to listen on through ``${PORT}`` and probing
``http://127.0.0.1:${PORT}/health`` before it runs the scenario. The
``google-genai`` live client always upgrades the WebSocket scheme to ``wss``
(TLS), while the runner's health probe is plain HTTP, so this process serves two
things on two ports:

- a plain-HTTP ``/health`` endpoint on ``${PORT}`` for the runner probe, and
- the Gemini Live ``BidiGenerateContent`` protocol over a secure WebSocket on
  ``${PORT} + 1``.

The scenario derives the WebSocket URL as the health port plus one (see
``scenario.py``), so the two stay in lock-step.

The WebSocket half speaks a deterministic subset of the Gemini Live
``BidiGenerateContent`` protocol against the real ``google-genai`` live client
(``client.aio.live.connect``). It runs as a standalone ``websockets`` asyncio
server (not Flask) because the client uses the ``websockets`` library over its
own bidi framing. The client always upgrades the connection to ``wss`` (TLS)
regardless of the configured base URL, so this server terminates TLS using a
checked-in self-signed certificate. The scenario connects with an unverified SSL
context, so the certificate's contents and hostname are irrelevant.

Server -> client turn sequence for one voice response:

1. ``{"serverContent": {"outputTranscription": {"text": ...}}}`` deltas -- the
   spoken audio transcript, streamed incrementally.
2. ``{"serverContent": {"modelTurn": {"parts": [{"inlineData": ...}]}}}`` -- the
   generated audio (PCM) for the turn.
3. ``{"serverContent": {"generationComplete": true}}``.
4. ``{"serverContent": {"turnComplete": true}, "usageMetadata": {...}}`` -- ends
   the turn and reports token usage with an ``AUDIO`` / ``TEXT`` modality
   breakdown for both prompt and response.

The first ``audioStreamEnd`` drives a simple spoken turn. A subsequent
``audioStreamEnd`` drives a tool-calling turn: the server emits a ``toolCall``
(and nothing else) so the client runs the tool and replies with a
``toolResponse``; the server then produces the spoken answer turn. This is the
sibling tool-call pattern used by Gemini Live 2.5.

When the requested model is a Gemini Live 3.x model, the very first
``audioStreamEnd`` drives the tool-calling turn directly (a single utterance
that resolves to a tool call and then the spoken answer), letting the client
model the tool call as a child of one generation.
"""

import argparse
import asyncio
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

_CERT_FILE = Path(__file__).with_name("mock_cert.pem")
_KEY_FILE = Path(__file__).with_name("mock_key.pem")

# Deterministic base64 stand-in for the PCM audio the model "speaks". The client
# decodes it to bytes; the scenario re-encodes it for the output message.
OUTPUT_AUDIO_B64 = "bW9jay1nZW1pbmktYXVkaW8="

TRANSCRIPT_DELTAS = ["It is ", "sunny and ", "about 72 degrees ", "in Seattle."]

# The tool the model asks the client to run on the tool-calling turn.
FUNCTION_CALL = {"id": "fc_mock_gemini_001", "name": "get_weather", "args": {"location": "Seattle"}}


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


async def _run_tool_call(ws):
    """Emit a tool call and nothing else; the client must reply with a toolResponse."""
    await _send(ws, {"toolCall": {"functionCalls": [FUNCTION_CALL]}})


async def _handler(ws):
    audio_turns = 0
    is_child_pattern = False
    async for raw in ws:
        message = json.loads(raw)
        if "setup" in message:
            # Gemini Live 3.x resolves a tool call within a single generation
            # (child pattern); 2.5 splits it into sibling generations. The mock
            # picks the behavior from the requested model.
            model = str((message["setup"] or {}).get("model", ""))
            is_child_pattern = "gemini-3" in model
            await _send(ws, {"setupComplete": {}})
        elif "tool_response" in message or "toolResponse" in message:
            # The client returned the tool result; the model now speaks its answer.
            await _run_turn(ws)
        elif "realtime_input" in message:
            realtime_input = message["realtime_input"] or {}
            # The client signals the end of the user's utterance; the model then
            # generates its spoken response for the accumulated audio.
            if realtime_input.get("audioStreamEnd"):
                audio_turns += 1
                if is_child_pattern:
                    # A single utterance that immediately requires a tool call.
                    await _run_tool_call(ws)
                elif audio_turns == 1:
                    await _run_turn(ws)
                else:
                    await _run_tool_call(ws)


class _HealthHandler(BaseHTTPRequestHandler):
    """Answers the runner's plain-HTTP health probe on the base port."""

    def do_GET(self):
        if self.path == "/health":
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        # Silence the default stderr access log; the runner captures our output.
        pass


def _start_health_server(host, port):
    server = ThreadingHTTPServer((host, port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    return server


async def _serve_ws(host, port):
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=_CERT_FILE, keyfile=_KEY_FILE)
    async with websockets.serve(_handler, host, port, ssl=ssl_ctx):
        await asyncio.Future()


def main():
    parser = argparse.ArgumentParser(description="Mock Google Gemini Live server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, required=True, help="Health port; the WebSocket serves on port + 1")
    args = parser.parse_args()
    _start_health_server(args.host, args.port)
    asyncio.run(_serve_ws(args.host, args.port + 1))


if __name__ == "__main__":
    main()
