"""Local HTTP server for Azure AI Content Safety analyze_text."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _ContentSafetyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/contentsafety/text:analyze?api-version=2024-09-01":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(content_length))
        if request.get("categories") != ["Hate"]:
            self.send_error(400)
            return

        response = {
            "categoriesAnalysis": [
                {
                    "category": "Hate",
                    "severity": 6,
                }
            ],
            "blocklistsMatch": [
                {
                    "blocklistName": "reference-blocklist",
                    "blocklistItemId": "reference-item-1",
                    "blocklistItemText": "blocked phrase",
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
def content_safety_mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ContentSafetyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
