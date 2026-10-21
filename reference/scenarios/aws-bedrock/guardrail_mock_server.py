"""Local HTTP server for the Bedrock Runtime ApplyGuardrail operation."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GUARDRAIL_ID = "grabc123"
GUARDRAIL_VERSION = "1"


class _GuardrailHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        expected_path = f"/guardrail/{GUARDRAIL_ID}/version/{GUARDRAIL_VERSION}/apply"
        if self.path != expected_path:
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(content_length))
        if request.get("source") != "INPUT":
            self.send_error(400)
            return

        response = {
            "usage": {
                "topicPolicyUnits": 0,
                "contentPolicyUnits": 1,
                "wordPolicyUnits": 0,
                "sensitiveInformationPolicyUnits": 0,
                "sensitiveInformationPolicyFreeUnits": 0,
                "contextualGroundingPolicyUnits": 0,
            },
            "action": "GUARDRAIL_INTERVENED",
            "actionReason": "Guardrail policy blocked harmful content",
            "outputs": [{"text": "Content blocked"}],
            "assessments": [
                {
                    "appliedGuardrailDetails": {
                        "guardrailId": GUARDRAIL_ID,
                        "guardrailVersion": GUARDRAIL_VERSION,
                    },
                    "contentPolicy": {
                        "filters": [
                            {
                                "type": "HATE",
                                "confidence": "HIGH",
                                "filterStrength": "HIGH",
                                "action": "BLOCKED",
                                "detected": True,
                            }
                        ]
                    },
                }
            ],
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        del format, args


@contextmanager
def guardrail_mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GuardrailHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
