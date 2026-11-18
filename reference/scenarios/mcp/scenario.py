"""Reference implementation for the Model Context Protocol (MCP) Python SDK."""

import asyncio
import contextlib
import json
import socket
import time
from collections.abc import AsyncIterator
from typing import Any

import anyio
import mcp.shared._otel as _mcp_otel
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import StreamableHTTPTransport, create_mcp_http_client
from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerMiddleware, ServerRequestContext
from mcp.shared._context_streams import create_context_streams
from mcp.shared._otel import extract_trace_context
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp_types import INVALID_PARAMS, CallToolResult
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import ValidationError
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_meter,
    reference_tracer,
    setup_otel,
)

# Suppress the SDK's built-in non-semconv spans ("MCP send ...") so the
# scenario validates the MCP semantic convention spans directly.
_mcp_otel._tracer = trace.NoOpTracer()

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_MCP_DURATION_BUCKETS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]

_client_operation_duration = _reference_meter.create_histogram(
    "mcp.client.operation.duration",
    unit="s",
    description=(
        "The duration of the MCP request or notification as observed on the sender "
        "from the time it was sent until the response or ack is received."
    ),
    explicit_bucket_boundaries_advisory=_MCP_DURATION_BUCKETS,
)
_server_operation_duration = _reference_meter.create_histogram(
    "mcp.server.operation.duration",
    unit="s",
    description=(
        "MCP request or notification duration as observed on the receiver "
        "from the time it was received until the result or ack is sent."
    ),
    explicit_bucket_boundaries_advisory=_MCP_DURATION_BUCKETS,
)


class ReferenceMCPServerMiddleware(ServerMiddleware[Any]):
    """MCP server middleware that emits `mcp.server` spans and `mcp.server.operation.duration`."""

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        if ctx.method in ("initialize", "notifications/initialized"):
            return await call_next(ctx)

        params = ctx.params or {}
        name = params.get("name")
        target = name if isinstance(name, str) else None
        span_name = f"{ctx.method} {target}" if target else ctx.method

        metric_attrs: dict[str, Any] = {
            "mcp.method.name": ctx.method,
            "mcp.protocol.version": ctx.protocol_version,
            "network.transport": "tcp",
            "network.protocol.name": "http",
        }
        if ctx.request is not None:
            http_version = ctx.request.scope.get("http_version")
            if http_version:
                metric_attrs["network.protocol.version"] = str(http_version)

        if ctx.method == "tools/call":
            metric_attrs["gen_ai.operation.name"] = "execute_tool"
            if target is not None:
                metric_attrs["gen_ai.tool.name"] = target
        elif ctx.method == "prompts/get" and target is not None:
            metric_attrs["gen_ai.prompt.name"] = target
        elif ctx.method == "resources/read" and params.get("uri") is not None:
            metric_attrs["mcp.resource.uri"] = str(params["uri"])

        span_attrs = dict(metric_attrs)
        if ctx.request_id is not None:
            span_attrs["jsonrpc.request.id"] = str(ctx.request_id)
        if ctx.request is not None:
            session_id = ctx.request.headers.get("mcp-session-id")
            if session_id:
                span_attrs["mcp.session.id"] = session_id
            if ctx.request.client:
                span_attrs["client.address"] = ctx.request.client.host
                span_attrs["client.port"] = ctx.request.client.port

        start_time = time.perf_counter()
        with _reference_tracer.start_as_current_span(
            span_name,
            kind=SpanKind.SERVER,
            attributes=span_attrs,
            context=extract_trace_context(ctx.meta),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                if ctx.method == "tools/call":
                    arguments = params.get("arguments")
                    if arguments is not None:
                        span.set_attribute("gen_ai.tool.call.arguments", arguments)
                elif ctx.method == "prompts/get":
                    prompt_args = params.get("arguments")
                    if isinstance(prompt_args, dict) and prompt_args:
                        span.set_attribute("gen_ai.prompt.variables", prompt_args)

                try:
                    result = await call_next(ctx)
                except MCPError as error:
                    code = str(error.error.code)
                    span.set_attribute("rpc.response.status_code", code)
                    metric_attrs["rpc.response.status_code"] = code
                    # Per mcp.server.status.attributes, caller errors (-32700, -32600,
                    # -32601, -32602, -32002) are not server errors, while other codes are.
                    if error.error.code not in (-32700, -32600, -32601, -32602, -32002):
                        span.set_attribute("error.type", code)
                        metric_attrs["error.type"] = code
                        span.set_status(StatusCode.ERROR, error.error.message)
                    raise
                except ValidationError:
                    code = str(INVALID_PARAMS)
                    span.set_attribute("rpc.response.status_code", code)
                    metric_attrs["rpc.response.status_code"] = code
                    raise
                except Exception as error:
                    error_type = type(error).__qualname__
                    span.set_attribute("error.type", error_type)
                    metric_attrs["error.type"] = error_type
                    span.set_status(StatusCode.ERROR, str(error))
                    raise

                if ctx.method == "tools/call":
                    is_error = (
                        result.is_error
                        if isinstance(result, CallToolResult)
                        else bool(result.get("isError"))
                        if isinstance(result, dict)
                        else False
                    )
                    structured_content = (
                        result.structured_content
                        if isinstance(result, CallToolResult)
                        else result.get("structuredContent")
                        if isinstance(result, dict)
                        else None
                    )
                    if is_error:
                        span.set_attribute("error.type", "tool_error")
                        metric_attrs["error.type"] = "tool_error"
                        span.set_status(StatusCode.ERROR)
                    elif structured_content is not None:
                        span.set_attribute("gen_ai.tool.call.result", structured_content)
                return result
            finally:
                assert "gen_ai.prompt.variables" not in metric_attrs
                _server_operation_duration.record(time.perf_counter() - start_time, metric_attrs)


def _build_mcp_server() -> MCPServer:
    mcp_server = MCPServer("weather-mcp")
    mcp_server._lowlevel_server.middleware[:] = [ReferenceMCPServerMiddleware()]

    @mcp_server.tool()
    def get_weather(location: str) -> dict[str, object]:
        """Get the current weather for a location."""
        return {"location": location, "temperature_f": 72, "conditions": "sunny"}

    @mcp_server.prompt()
    def analyze_weather(user_name: str, language: str) -> str:
        """Build a localized weather analysis prompt."""
        return f"Summarize the weather forecast for {user_name} in {language}."

    @mcp_server.resource("file:///weather/seattle.json")
    def seattle_weather() -> str:
        """Current weather snapshot for Seattle."""
        return json.dumps({"location": "Seattle", "temperature_f": 72, "conditions": "sunny"})

    return mcp_server


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.asynccontextmanager
async def _serve_mcp(mcp_server: MCPServer) -> AsyncIterator[str]:
    port = _free_port()
    app = mcp_server.streamable_http_app(json_response=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            await serving
            raise RuntimeError("MCP server exited before starting")
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await serving


@contextlib.asynccontextmanager
async def _connect_session(url: str) -> AsyncIterator[tuple[ClientSession, StreamableHTTPTransport]]:
    http_client = create_mcp_http_client()
    transport = StreamableHTTPTransport(url)
    async with http_client:
        read_stream_writer, read_stream = create_context_streams[SessionMessage | Exception](0)
        write_stream, write_stream_reader = create_context_streams[SessionMessage](0)
        async with (
            read_stream_writer,
            read_stream,
            write_stream,
            write_stream_reader,
            anyio.create_task_group() as tg,
        ):

            def start_get_stream() -> None:
                tg.start_soon(transport.handle_get_stream, http_client, read_stream_writer)

            tg.start_soon(
                transport.post_writer,
                http_client,
                write_stream_reader,
                read_stream_writer,
                write_stream,
                start_get_stream,
                tg,
            )
            try:
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session, transport
            finally:
                if transport.session_id:
                    await transport.terminate_session(http_client)
                tg.cancel_scope.cancel()


def _client_metric_attributes(
    method: str,
    session: ClientSession,
    host: str | None,
    port: int | None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "mcp.method.name": method,
        "network.transport": "tcp",
        "network.protocol.name": "http",
        "network.protocol.version": "1.1",
    }
    if session._negotiated_version:
        attributes["mcp.protocol.version"] = session._negotiated_version
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _client_span_attributes(
    metric_attrs: dict[str, Any],
    session: ClientSession,
    transport: StreamableHTTPTransport,
) -> dict[str, Any]:
    span_attrs = dict(metric_attrs)
    # JSONRPCDispatcher._allocate_id() increments _next_id before returning the wire id.
    span_attrs["jsonrpc.request.id"] = str(session._dispatcher._next_id + 1)
    if transport.session_id:
        span_attrs["mcp.session.id"] = transport.session_id
    return span_attrs


async def run_tool_call_reference(
    session: ClientSession,
    transport: StreamableHTTPTransport,
    host: str | None,
    port: int | None,
) -> None:
    """Scenario: MCP tools/call."""
    print("  [tools/call] MCP tool call")
    tool_name = "get_weather"
    arguments = {"location": "Seattle"}
    metric_attrs = _client_metric_attributes("tools/call", session, host, port)
    metric_attrs["gen_ai.operation.name"] = "execute_tool"
    metric_attrs["gen_ai.tool.name"] = tool_name
    span_attrs = _client_span_attributes(metric_attrs, session, transport)

    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        f"tools/call {tool_name}",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            span.set_attribute("gen_ai.tool.call.arguments", arguments)
            result = await session.call_tool(tool_name, arguments)
            if result.structured_content is not None:
                span.set_attribute("gen_ai.tool.call.result", result.structured_content)
        finally:
            _client_operation_duration.record(time.perf_counter() - start_time, metric_attrs)
    print(f"    -> {result.structured_content}")


async def run_prompt_get_reference(
    session: ClientSession,
    transport: StreamableHTTPTransport,
    host: str | None,
    port: int | None,
) -> None:
    """Scenario: MCP prompts/get with prompt variables."""
    print("  [prompts/get] MCP prompt retrieval")
    prompt_name = "analyze_weather"
    prompt_arguments = {"user_name": "Alice", "language": "French"}
    metric_attrs = _client_metric_attributes("prompts/get", session, host, port)
    metric_attrs["gen_ai.prompt.name"] = prompt_name
    span_attrs = _client_span_attributes(metric_attrs, session, transport)

    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        f"prompts/get {prompt_name}",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            span.set_attribute("gen_ai.prompt.variables", prompt_arguments)
            prompt_result = await session.get_prompt(prompt_name, prompt_arguments)
        finally:
            assert "gen_ai.prompt.variables" not in metric_attrs
            _client_operation_duration.record(time.perf_counter() - start_time, metric_attrs)
    print(f"    -> {len(prompt_result.messages)} prompt message(s)")


async def run_resource_read_reference(
    session: ClientSession,
    transport: StreamableHTTPTransport,
    host: str | None,
    port: int | None,
) -> None:
    """Scenario: MCP resources/read."""
    print("  [resources/read] MCP resource read")
    resource_uri = "file:///weather/seattle.json"
    metric_attrs = _client_metric_attributes("resources/read", session, host, port)
    metric_attrs["mcp.resource.uri"] = resource_uri
    span_attrs = _client_span_attributes(metric_attrs, session, transport)

    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        "resources/read",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ):
        try:
            resource_result = await session.read_resource(resource_uri)
        finally:
            _client_operation_duration.record(time.perf_counter() - start_time, metric_attrs)
    print(f"    -> {len(resource_result.contents)} resource content item(s)")


async def run_tool_call_error_reference(
    session: ClientSession,
    transport: StreamableHTTPTransport,
    host: str | None,
    port: int | None,
) -> None:
    """Scenario: MCP tool call error (`isError=True`) and JSON-RPC resource error."""
    print("  [tools/call error] MCP unknown tool error")
    tool_name = "missing_tool"
    metric_attrs = _client_metric_attributes("tools/call", session, host, port)
    metric_attrs["gen_ai.operation.name"] = "execute_tool"
    metric_attrs["gen_ai.tool.name"] = tool_name
    span_attrs = _client_span_attributes(metric_attrs, session, transport)

    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        f"tools/call {tool_name}",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            result = await session.call_tool(tool_name, {"location": "Seattle"})
            if result.is_error:
                span.set_attribute("error.type", "tool_error")
                metric_attrs["error.type"] = "tool_error"
                span.set_status(StatusCode.ERROR)
                print("    -> CallToolResult isError=True (error.type=tool_error)")
        except MCPError as error:
            code = str(error.error.code)
            span.set_attribute("error.type", code)
            span.set_attribute("rpc.response.status_code", code)
            metric_attrs["error.type"] = code
            metric_attrs["rpc.response.status_code"] = code
            span.set_status(StatusCode.ERROR, error.error.message)
        finally:
            _client_operation_duration.record(time.perf_counter() - start_time, metric_attrs)

    missing_uri = "file:///weather/missing.json"
    res_metric_attrs = _client_metric_attributes("resources/read", session, host, port)
    res_metric_attrs["mcp.resource.uri"] = missing_uri
    res_span_attrs = _client_span_attributes(res_metric_attrs, session, transport)

    res_start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        "resources/read",
        kind=SpanKind.CLIENT,
        attributes=res_span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            await session.read_resource(missing_uri)
        except MCPError as error:
            code = str(error.error.code)
            span.set_attribute("error.type", code)
            span.set_attribute("rpc.response.status_code", code)
            res_metric_attrs["error.type"] = code
            res_metric_attrs["rpc.response.status_code"] = code
            span.set_status(StatusCode.ERROR, error.error.message)
            print(f"    -> JSON-RPC error {code}: {error.error.message}")
        finally:
            _client_operation_duration.record(time.perf_counter() - res_start_time, res_metric_attrs)


async def run_scenarios() -> None:
    mcp_server = _build_mcp_server()
    async with _serve_mcp(mcp_server) as url:
        host, port = mock_server_host_port(url)
        async with _connect_session(url) as (session, transport):
            await run_tool_call_reference(session, transport, host, port)
            await run_prompt_get_reference(session, transport, host, port)
            await run_resource_read_reference(session, transport, host, port)
            await run_tool_call_error_reference(session, transport, host, port)


def main() -> None:
    print("=== Reference Implementation: MCP Python SDK ===")
    tp, lp, mp = setup_otel()
    span_exporter = InMemorySpanExporter()
    tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    asyncio.run(run_scenarios())

    finished_spans = span_exporter.get_finished_spans()
    client_ids = {
        (s.context.span_id, s.attributes["mcp.method.name"]): s.attributes["jsonrpc.request.id"]
        for s in finished_spans
        if s.kind == SpanKind.CLIENT and s.attributes
    }
    server_ids = {
        (s.parent.span_id, s.attributes["mcp.method.name"]): s.attributes["jsonrpc.request.id"]
        for s in finished_spans
        if s.kind == SpanKind.SERVER
        and s.parent
        and s.attributes
        and (s.parent.span_id, s.attributes["mcp.method.name"]) in client_ids
    }
    assert client_ids == server_ids, f"Mismatched client/server request IDs: {client_ids} != {server_ids}"

    prompt_spans = [s for s in finished_spans if s.attributes and s.attributes.get("mcp.method.name") == "prompts/get"]
    assert len(prompt_spans) == 2, f"Expected client and server prompts/get spans, got {len(prompt_spans)}"
    for prompt_span in prompt_spans:
        assert prompt_span.attributes and "gen_ai.prompt.variables" in prompt_span.attributes

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
