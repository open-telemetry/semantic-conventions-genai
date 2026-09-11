"""Minimal A2A JSON-RPC mock for the A2A Python reference scenario."""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PROTOCOL_VERSION = "1.0"


def _task(
    task_id: str = "task-calendar-summary",
    context_id: str = "ctx-calendar",
    state: str = "TASK_STATE_COMPLETED",
) -> dict[str, Any]:
    return {
        "id": task_id,
        "contextId": context_id,
        "status": {"state": state},
        "artifacts": [
            {
                "artifactId": "art-001",
                "parts": [{"text": "Calendar summary artifact."}],
            }
        ],
    }


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


class A2ARequestHandler(BaseHTTPRequestHandler):
    """Serve only the JSON-RPC operations exercised by the scenario."""

    tracer: Any | None = None
    span_kind: Any | None = None
    agent_card: Any | None = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(HTTPStatus.OK)
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/a2a":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(content_length))
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        with self._start_span(method, params) as span:
            if method == "SendMessage":
                task = _task()
                self._set_task_attributes(span, task)
                self._send_json(
                    _response(
                        request_id,
                        {
                            "task": {
                                **task,
                                "history": [
                                    {
                                        "messageId": "msg-agent-1",
                                        "role": "ROLE_AGENT",
                                        "taskId": "task-calendar-summary",
                                        "parts": [{"text": "Your afternoon is open."}],
                                    }
                                ],
                            }
                        },
                    )
                )
                return

            if method == "SendStreamingMessage":
                self._set_task_attributes(
                    span,
                    _task(
                        task_id="task-streaming",
                        context_id="ctx-streaming",
                    ),
                )
                self._send_stream(request_id)
                return

            if method == "GetTask":
                task = _task(task_id=params.get("id", "task-calendar-summary"))
                self._set_task_attributes(span, task)
                self._send_json(_response(request_id, task))
                return

            self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )

    @contextmanager
    def _start_span(self, method: str | None, params: dict[str, Any]) -> Generator[Any | None, None, None]:
        if self.tracer is None or self.span_kind is None:
            yield None
            return

        message = params.get("message") or {}
        host, port = self.server.server_address[:2]
        client_host, client_port = self.client_address
        attributes: dict[str, Any] = {
            "a2a.method.name": method,
            "a2a.protocol.version": PROTOCOL_VERSION,
            "a2a.tenant": params.get("tenant"),
            "a2a.message.id": message.get("messageId"),
            "a2a.message.reference_task_ids": message.get("referenceTaskIds"),
            "server.address": host,
            "server.port": port,
            "client.address": client_host,
            "client.port": client_port,
        }
        attributes.update(_agent_attributes(self.agent_card))
        attributes = {key: value for key, value in attributes.items() if value not in (None, [])}
        with self.tracer.start_as_current_span(method or "A2A", kind=self.span_kind, attributes=attributes) as span:
            yield span

    @staticmethod
    def _set_task_attributes(span: Any | None, task: dict[str, Any]) -> None:
        if span is None:
            return
        span.set_attribute("a2a.task.id", task["id"])
        span.set_attribute("a2a.task.state", task["status"]["state"])
        span.set_attribute("gen_ai.conversation.id", task["contextId"])

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, request_id: Any) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for state in ("TASK_STATE_WORKING", "TASK_STATE_COMPLETED"):
            event = _response(
                request_id,
                {
                    "statusUpdate": {
                        "taskId": "task-streaming",
                        "contextId": "ctx-streaming",
                        "status": {"state": state},
                    }
                },
            )
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        return


def _agent_attributes(card: Any | None) -> dict[str, str]:
    if card is None:
        return {}
    return {
        key: value
        for key, value in {
            "gen_ai.agent.name": getattr(card, "name", None),
            "gen_ai.agent.description": getattr(card, "description", None),
            "gen_ai.agent.version": getattr(card, "version", None),
        }.items()
        if value
    }


@contextmanager
def running_mock_server(
    *,
    tracer: Any,
    span_kind: Any,
    agent_card_factory: Callable[[str], Any],
) -> Generator[str, None, None]:
    """Run the A2A mock in-process so its spans reach the scenario exporter."""
    handler = type(
        "InstrumentedA2ARequestHandler",
        (A2ARequestHandler,),
        {"tracer": tracer, "span_kind": span_kind},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/a2a"
    handler.agent_card = agent_card_factory(url)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield url
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), A2ARequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
