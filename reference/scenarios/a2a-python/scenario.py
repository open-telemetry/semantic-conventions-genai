"""Reference implementation for A2A Python SDK."""

import asyncio
import json
import socket
from contextlib import asynccontextmanager

import httpx
import uvicorn
from a2a import types as a2a_types
from a2a.client import ClientConfig, create_client
from a2a.server.routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.utils.constants import TransportProtocol
from agent import agent_card, request_handler
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.trace import SpanKind, get_current_span, use_span
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

RPC_PATH = "/a2a"
# One tenant per server, so the standalone and transport-enriched spans of a
# run stay distinguishable in the recorded telemetry.
TENANT = "billing"
TENANT_OVER_HTTP = "billing-http"

_reference_tracer = reference_tracer()

ROLE_USER = a2a_types.Role.Value("ROLE_USER")


def _message(text: str, *, message_id: str, reference_task_ids: list[str] | None = None):
    return a2a_types.Message(
        message_id=message_id,
        parts=[a2a_types.Part(text=text)],
        role=ROLE_USER,
        reference_task_ids=reference_task_ids or [],
    )


def _task_state_value(state: int) -> str:
    return a2a_types.TaskState.Name(state)


def _jsonrpc_interface(card: a2a_types.AgentCard) -> a2a_types.AgentInterface:
    """The card interface the JSON-RPC transport serves, as the SDK selects it."""
    return next(i for i in card.supported_interfaces if i.protocol_binding == TransportProtocol.JSONRPC)


class ReferenceJsonRpcDispatcher(JsonRpcDispatcher):
    """The A2A server-side instrumentation point.

    `handle_requests` is where `a2a-sdk` turns an inbound HTTP POST into an A2A
    method call, so it is the one place server instrumentation sees both the
    decoded request and the response produced for it. The Agent Card is the one
    the application handed the SDK when it built this server.

    `enrich_transport_span` selects between the two cases the conventions
    describe. When the A2A request is handled inside an instrumented transport
    server call, the A2A attributes are stamped onto that span and no second
    server span is created (`a2a.http.server`). When there is no such span to
    find, a standalone `a2a.server` span is reported instead.
    """

    def __init__(
        self,
        request_handler,
        card: a2a_types.AgentCard,
        *,
        enrich_transport_span: bool = False,
    ) -> None:
        super().__init__(request_handler=request_handler)
        self._card = card
        self._enrich_transport_span = enrich_transport_span

    async def handle_requests(self, request: Request) -> Response:
        body = await request.json()
        method = body["method"]
        params = body.get("params") or {}
        message = params.get("message") or {}
        interface = _jsonrpc_interface(self._card)
        span_attrs = {
            "a2a.method.name": method,
            "a2a.protocol.version": interface.protocol_version,
            "gen_ai.agent.name": self._card.name,
            "gen_ai.agent.description": self._card.description,
            "gen_ai.agent.version": self._card.version,
            "server.address": request.url.hostname,
            "server.port": request.url.port,
        }
        if params.get("tenant"):
            span_attrs["a2a.tenant"] = params["tenant"]
        if message.get("messageId"):
            span_attrs["a2a.message.id"] = message["messageId"]
        if message.get("referenceTaskIds"):
            span_attrs["a2a.message.reference_task_ids"] = message["referenceTaskIds"]
        if params.get("id"):
            span_attrs["a2a.task.id"] = params["id"]
        if request.client:
            span_attrs["client.address"] = request.client.host
            span_attrs["client.port"] = request.client.port

        if self._enrich_transport_span:
            # The transport server span is already in flight and already carries
            # the HTTP attributes, so A2A only adds its own and renames it.
            span = get_current_span()
            span.update_name(method)
            span.set_attributes(span_attrs)
            response = await super().handle_requests(request)
        else:
            span = _reference_tracer.start_span(method, kind=SpanKind.SERVER, attributes=span_attrs)
            with use_span(span, end_on_exit=False):
                response = await super().handle_requests(request)

        events = getattr(response, "body_iterator", None)
        if events is None:
            result = json.loads(response.body).get("result") or {}
            task = result.get("task") or result
            span.set_attribute("a2a.task.id", task["id"])
            span.set_attribute("a2a.task.state", task["status"]["state"])
            span.set_attribute("gen_ai.conversation.id", task["contextId"])
            if not self._enrich_transport_span:
                span.end()
            return response

        # A streaming call is not served until the client has drained the
        # stream, so the span stays open until the last event is yielded.
        async def traced_events():
            try:
                async for event in events:
                    update = (json.loads(event["data"]).get("result") or {}).get("statusUpdate")
                    if update:
                        span.set_attribute("a2a.task.id", update["taskId"])
                        span.set_attribute("a2a.task.state", update["status"]["state"])
                        span.set_attribute("gen_ai.conversation.id", update["contextId"])
                    yield event
            finally:
                if not self._enrich_transport_span:
                    span.end()

        response.body_iterator = traced_events()
        return response


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _agent_app(card: a2a_types.AgentCard, *, enrich_transport_span: bool):
    dispatcher = ReferenceJsonRpcDispatcher(request_handler(card), card, enrich_transport_span=enrich_transport_span)
    app = Starlette(
        routes=[
            Route(RPC_PATH, endpoint=dispatcher.handle_requests, methods=["POST"]),
            *create_agent_card_routes(card),
        ]
    )
    if not enrich_transport_span:
        return app
    # A transport server span only exists when the ASGI app is instrumented;
    # this is the span the A2A attributes are stamped onto.
    return OpenTelemetryMiddleware(app, exclude_spans=["receive", "send"])


@asynccontextmanager
async def _serve(app, port: int):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        yield
    finally:
        server.should_exit = True
        await serving


@asynccontextmanager
async def serve_agents():
    """Serve the agent twice, once per server-span case, and yield both cards.

    The plain server has no transport instrumentation, so A2A reports a
    standalone `a2a.server` span. The instrumented one produces an
    `http.server` span that A2A enriches in place instead.
    """
    standalone_port, over_http_port = _free_port(), _free_port()
    standalone = agent_card(f"http://127.0.0.1:{standalone_port}{RPC_PATH}", tenant=TENANT)
    over_http = agent_card(f"http://127.0.0.1:{over_http_port}{RPC_PATH}", tenant=TENANT_OVER_HTTP)
    async with (
        _serve(_agent_app(standalone, enrich_transport_span=False), standalone_port),
        _serve(_agent_app(over_http, enrich_transport_span=True), over_http_port),
    ):
        yield standalone, over_http


async def _create_a2a_client(card: a2a_types.AgentCard, *, streaming: bool):
    httpx_client = httpx.AsyncClient()
    return await create_client(card, ClientConfig(streaming=streaming, httpx_client=httpx_client))


async def run_message_send_reference(card: a2a_types.AgentCard) -> str:
    """Scenario: A2A JSON-RPC send_message with a task response."""
    print("  [send_message] A2A JSON-RPC send_message")
    method = "SendMessage"
    interface = _jsonrpc_interface(card)
    request = a2a_types.SendMessageRequest(
        tenant=interface.tenant,
        message=_message(
            "Summarize my calendar.",
            message_id="msg-user-1",
            reference_task_ids=["task-calendar-prior"],
        ),
    )

    host, port = mock_server_host_port(interface.url)
    span_attrs = {
        "a2a.method.name": method,
        "a2a.protocol.version": interface.protocol_version,
        "a2a.tenant": request.tenant,
        "a2a.message.id": request.message.message_id,
        "a2a.message.reference_task_ids": request.message.reference_task_ids,
        "gen_ai.agent.name": card.name,
        "gen_ai.agent.description": card.description,
        "gen_ai.agent.version": card.version,
    }
    if host:
        span_attrs["server.address"] = host
    if port is not None:
        span_attrs["server.port"] = port
    with _reference_tracer.start_as_current_span(method, kind=SpanKind.CLIENT, attributes=span_attrs) as span:
        async with await _create_a2a_client(card, streaming=False) as client:
            response = await anext(client.send_message(request))
        task = response.task
        task_state = _task_state_value(task.status.state)
        span.set_attribute("a2a.task.id", task.id)
        span.set_attribute("a2a.task.state", task_state)
        span.set_attribute("gen_ai.conversation.id", task.context_id)
    print(f"    -> {task.id} {task_state}")
    return task.id


async def run_message_stream_reference(card: a2a_types.AgentCard) -> None:
    """Scenario: A2A JSON-RPC send_streaming_message with SSE task status events."""
    print("  [send_streaming_message] A2A JSON-RPC send_streaming_message")
    method = "SendStreamingMessage"
    interface = _jsonrpc_interface(card)
    request = a2a_types.SendMessageRequest(
        tenant=interface.tenant,
        message=_message("Track this task.", message_id="msg-user-2"),
    )

    event_count = 0
    task_id = None
    context_id = None
    task_state = None
    host, port = mock_server_host_port(interface.url)
    span_attrs = {
        "a2a.method.name": method,
        "a2a.protocol.version": interface.protocol_version,
        "a2a.tenant": request.tenant,
        "a2a.message.id": request.message.message_id,
        "gen_ai.agent.name": card.name,
        "gen_ai.agent.description": card.description,
        "gen_ai.agent.version": card.version,
    }
    if host:
        span_attrs["server.address"] = host
    if port is not None:
        span_attrs["server.port"] = port
    with _reference_tracer.start_as_current_span(method, kind=SpanKind.CLIENT, attributes=span_attrs) as span:
        async with await _create_a2a_client(card, streaming=True) as client:
            async for event in client.send_message(request):
                event_count += 1
                if event.HasField("status_update"):
                    task_id = event.status_update.task_id
                    context_id = event.status_update.context_id
                    task_state = _task_state_value(event.status_update.status.state)

        assert task_id is not None
        assert task_state is not None
        assert context_id is not None
        span.set_attribute("a2a.task.id", task_id)
        span.set_attribute("a2a.task.state", task_state)
        span.set_attribute("gen_ai.conversation.id", context_id)
    print(f"    -> {event_count} events")


async def run_tasks_get_reference(card: a2a_types.AgentCard, task_id: str) -> None:
    """Scenario: A2A JSON-RPC get_task."""
    print("  [get_task] A2A JSON-RPC get_task")
    method = "GetTask"
    interface = _jsonrpc_interface(card)
    request = a2a_types.GetTaskRequest(tenant=interface.tenant, id=task_id)

    host, port = mock_server_host_port(interface.url)
    span_attrs = {
        "a2a.method.name": method,
        "a2a.protocol.version": interface.protocol_version,
        "a2a.tenant": request.tenant,
        "a2a.task.id": request.id,
        "gen_ai.agent.name": card.name,
        "gen_ai.agent.description": card.description,
        "gen_ai.agent.version": card.version,
    }
    if host:
        span_attrs["server.address"] = host
    if port is not None:
        span_attrs["server.port"] = port
    with _reference_tracer.start_as_current_span(method, kind=SpanKind.CLIENT, attributes=span_attrs) as span:
        async with await _create_a2a_client(card, streaming=False) as client:
            task = await client.get_task(request)
        task_state = _task_state_value(task.status.state)
        span.set_attribute("a2a.task.state", task_state)
        span.set_attribute("gen_ai.conversation.id", task.context_id)
    print(f"    -> {request.id} {task_state}")


async def run_server_over_http_reference(card: a2a_types.AgentCard) -> None:
    """Scenario: A2A requests served inside an instrumented HTTP server call.

    Drives the instrumented server so its `http.server` spans are enriched in
    place. The client side is already covered by the scenarios above, so these
    calls deliberately report no client span of their own.
    """
    print("  [server_over_http] A2A requests handled within an HTTP server span")
    interface = _jsonrpc_interface(card)
    send = a2a_types.SendMessageRequest(
        tenant=interface.tenant,
        message=_message("Summarize my calendar.", message_id="msg-user-3"),
    )
    async with await _create_a2a_client(card, streaming=False) as client:
        task = (await anext(client.send_message(send))).task

    stream = a2a_types.SendMessageRequest(
        tenant=interface.tenant,
        message=_message("Track this task.", message_id="msg-user-4"),
    )
    events = 0
    async with await _create_a2a_client(card, streaming=True) as client:
        async for _ in client.send_message(stream):
            events += 1
    print(f"    -> {task.id} {_task_state_value(task.status.state)}, {events} streamed events")


async def run_scenarios() -> None:
    async with serve_agents() as (standalone, over_http):
        task_id = await run_message_send_reference(standalone)
        await run_message_stream_reference(standalone)
        await run_tasks_get_reference(standalone, task_id)
        await run_server_over_http_reference(over_http)


def main() -> None:
    print("=== Reference Implementation: A2A Python SDK ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_scenarios())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
