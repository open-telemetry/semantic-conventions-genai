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
from mcp.shared.jsonrpc_dispatcher import JSONRPCDispatcher
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


class ReferenceMCPClientSession(ClientSession):
    """MCP client session that emits `mcp.client` spans and `mcp.client.operation.duration` per request."""

    def __init__(
        self,
        read_stream: Any,
        write_stream: Any,
        *,
        transport: StreamableHTTPTransport,
        host: str | None,
        port: int | None,
    ) -> None:
        super().__init__(read_stream, write_stream)
        self._transport = transport
        self._host = host
        self._port = port

    async def send_request(
        self,
        request: Any,
        result_type: Any,
        request_read_timeout_seconds: float | None = None,
        metadata: Any = None,
        progress_callback: Any = None,
    ) -> Any:
        data = request.model_dump(by_alias=True, mode="json", exclude_none=True)
        method: str = data["method"]
        if method == "initialize":
            return await super().send_request(
                request,
                result_type,
                request_read_timeout_seconds=request_read_timeout_seconds,
                metadata=metadata,
                progress_callback=progress_callback,
            )

        params: dict[str, Any] = data.get("params") or {}
        name = params.get("name")
        target = name if isinstance(name, str) else None
        span_name = f"{method} {target}" if target else method

        metric_attrs: dict[str, Any] = {
            "mcp.method.name": method,
            "network.transport": "tcp",
            "network.protocol.name": "http",
            "network.protocol.version": "1.1",
        }
        if self._negotiated_version:
            metric_attrs["mcp.protocol.version"] = self._negotiated_version
        if self._host:
            metric_attrs["server.address"] = self._host
        if self._port is not None:
            metric_attrs["server.port"] = self._port

        if method == "tools/call":
            metric_attrs["gen_ai.operation.name"] = "execute_tool"
            if target is not None:
                metric_attrs["gen_ai.tool.name"] = target
        elif method == "prompts/get" and target is not None:
            metric_attrs["gen_ai.prompt.name"] = target
        elif method == "resources/read" and params.get("uri") is not None:
            metric_attrs["mcp.resource.uri"] = str(params["uri"])

        span_attrs = dict(metric_attrs)
        # JSONRPCDispatcher._allocate_id() increments _next_id before returning the wire id.
        if isinstance(self._dispatcher, JSONRPCDispatcher):
            span_attrs["jsonrpc.request.id"] = str(self._dispatcher._next_id + 1)
        if self._transport.session_id:
            span_attrs["mcp.session.id"] = self._transport.session_id

        start_time = time.perf_counter()
        with _reference_tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attrs,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                if method == "tools/call":
                    arguments = params.get("arguments")
                    if arguments is not None:
                        span.set_attribute("gen_ai.tool.call.arguments", arguments)
                elif method == "prompts/get":
                    prompt_args = params.get("arguments")
                    if isinstance(prompt_args, dict) and prompt_args:
                        span.set_attribute("gen_ai.prompt.variables", prompt_args)

                try:
                    result = await super().send_request(
                        request,
                        result_type,
                        request_read_timeout_seconds=request_read_timeout_seconds,
                        metadata=metadata,
                        progress_callback=progress_callback,
                    )
                except MCPError as error:
                    code = str(error.error.code)
                    span.set_attribute("error.type", code)
                    span.set_attribute("rpc.response.status_code", code)
                    metric_attrs["error.type"] = code
                    metric_attrs["rpc.response.status_code"] = code
                    span.set_status(StatusCode.ERROR, error.error.message)
                    raise
                except Exception as error:
                    error_type = type(error).__qualname__
                    span.set_attribute("error.type", error_type)
                    metric_attrs["error.type"] = error_type
                    span.set_status(StatusCode.ERROR, str(error))
                    raise

                if method == "tools/call" and isinstance(result, CallToolResult):
                    if result.is_error:
                        span.set_attribute("error.type", "tool_error")
                        metric_attrs["error.type"] = "tool_error"
                        span.set_status(StatusCode.ERROR)
                    elif result.structured_content is not None:
                        span.set_attribute("gen_ai.tool.call.result", result.structured_content)
                return result
            finally:
                assert "gen_ai.prompt.variables" not in metric_attrs
                _client_operation_duration.record(time.perf_counter() - start_time, metric_attrs)


@contextlib.asynccontextmanager
async def _connect_session(
    url: str,
    host: str | None,
    port: int | None,
) -> AsyncIterator[ReferenceMCPClientSession]:
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
                async with ReferenceMCPClientSession(
                    read_stream,
                    write_stream,
                    transport=transport,
                    host=host,
                    port=port,
                ) as session:
                    await session.initialize()
                    yield session
            finally:
                if transport.session_id:
                    await transport.terminate_session(http_client)
                tg.cancel_scope.cancel()


async def run_tool_list_reference(session: ReferenceMCPClientSession) -> None:
    """Scenario: MCP tools/list (populates client output-schema cache before tools/call)."""
    print("  [tools/list] MCP tool listing")
    result = await session.list_tools()
    print(f"    -> {len(result.tools)} tool(s)")


async def run_tool_call_reference(session: ReferenceMCPClientSession) -> None:
    """Scenario: MCP tools/call."""
    print("  [tools/call] MCP tool call")
    result = await session.call_tool("get_weather", {"location": "Seattle"})
    print(f"    -> {result.structured_content}")


async def run_prompt_get_reference(session: ReferenceMCPClientSession) -> None:
    """Scenario: MCP prompts/get with prompt variables."""
    print("  [prompts/get] MCP prompt retrieval")
    prompt_result = await session.get_prompt("analyze_weather", {"user_name": "Alice", "language": "French"})
    print(f"    -> {len(prompt_result.messages)} prompt message(s)")


async def run_resource_read_reference(session: ReferenceMCPClientSession) -> None:
    """Scenario: MCP resources/read."""
    print("  [resources/read] MCP resource read")
    resource_result = await session.read_resource("file:///weather/seattle.json")
    print(f"    -> {len(resource_result.contents)} resource content item(s)")


async def run_tool_call_error_reference(session: ReferenceMCPClientSession) -> None:
    """Scenario: MCP tool call error (`isError=True`) and JSON-RPC resource error."""
    print("  [tools/call error] MCP unknown tool error")
    result = await session.call_tool("missing_tool", {"location": "Seattle"})
    assert result.is_error
    print("    -> CallToolResult isError=True (error.type=tool_error)")

    missing_uri = "file:///weather/missing.json"
    try:
        await session.read_resource(missing_uri)
    except MCPError as error:
        print(f"    -> JSON-RPC error {error.error.code}: {error.error.message}")
    else:
        raise AssertionError(f"Expected MCPError for {missing_uri}")


async def run_scenarios() -> None:
    mcp_server = _build_mcp_server()
    async with _serve_mcp(mcp_server) as url:
        host, port = mock_server_host_port(url)
        async with _connect_session(url, host, port) as session:
            await run_tool_list_reference(session)
            await run_tool_call_reference(session)
            await run_prompt_get_reference(session)
            await run_resource_read_reference(session)
            await run_tool_call_error_reference(session)


def main() -> None:
    print("=== Reference Implementation: MCP Python SDK ===")
    tp, lp, mp = setup_otel()
    span_exporter = InMemorySpanExporter()
    tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    asyncio.run(run_scenarios())

    finished_spans = span_exporter.get_finished_spans()
    client_spans = [s for s in finished_spans if s.kind == SpanKind.CLIENT and s.attributes]
    server_spans = [s for s in finished_spans if s.kind == SpanKind.SERVER and s.attributes]
    assert len(client_spans) == len(server_spans), (
        f"Expected 1:1 client/server spans, got {len(client_spans)} client and {len(server_spans)} server"
    )
    client_span_ids = {s.context.span_id for s in client_spans}
    assert all(s.parent is None or s.parent.span_id not in client_span_ids for s in client_spans), (
        "Client MCP spans should not nest one JSON-RPC request inside another"
    )
    client_ids = {
        (s.context.span_id, s.attributes["mcp.method.name"]): s.attributes["jsonrpc.request.id"] for s in client_spans
    }
    server_ids = {
        (s.parent.span_id, s.attributes["mcp.method.name"]): s.attributes["jsonrpc.request.id"]
        for s in server_spans
        if s.parent
    }
    assert client_ids == server_ids, f"Mismatched client/server request IDs: {client_ids} != {server_ids}"

    prompt_spans = [s for s in finished_spans if s.attributes and s.attributes.get("mcp.method.name") == "prompts/get"]
    assert len(prompt_spans) == 2, f"Expected client and server prompts/get spans, got {len(prompt_spans)}"
    for prompt_span in prompt_spans:
        assert prompt_span.attributes and "gen_ai.prompt.variables" in prompt_span.attributes

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
