"""Reference implementation for the Model Context Protocol (MCP) Python SDK."""

import asyncio
import contextlib
import json
import socket
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
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import ValidationError
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

# Suppress the SDK's built-in non-semconv spans ("MCP send ...") so the
# scenario validates the MCP semantic convention spans directly.
_mcp_otel._tracer = trace.NoOpTracer()

_reference_tracer = reference_tracer()


class ReferenceMCPServerMiddleware(ServerMiddleware[Any]):
    """MCP server middleware that emits `mcp.server` spans."""

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        if ctx.method in ("initialize", "notifications/initialized"):
            return await call_next(ctx)

        params = ctx.params or {}
        name = params.get("name")
        target = name if isinstance(name, str) else None
        span_name = f"{ctx.method} {target}" if target else ctx.method

        attributes: dict[str, Any] = {
            "mcp.method.name": ctx.method,
            "mcp.protocol.version": ctx.protocol_version,
            "network.transport": "tcp",
            "network.protocol.name": "http",
        }
        if ctx.request_id is not None:
            attributes["jsonrpc.request.id"] = str(ctx.request_id)
        if ctx.request is not None:
            http_version = ctx.request.scope.get("http_version")
            if http_version:
                attributes["network.protocol.version"] = str(http_version)
            session_id = ctx.request.headers.get("mcp-session-id")
            if session_id:
                attributes["mcp.session.id"] = session_id
            if ctx.request.client:
                attributes["client.address"] = ctx.request.client.host
                attributes["client.port"] = ctx.request.client.port

        if ctx.method == "tools/call":
            attributes["gen_ai.operation.name"] = "execute_tool"
            if target is not None:
                attributes["gen_ai.tool.name"] = target
        elif ctx.method == "prompts/get" and target is not None:
            attributes["gen_ai.prompt.name"] = target
        elif ctx.method == "resources/read" and params.get("uri") is not None:
            attributes["mcp.resource.uri"] = str(params["uri"])

        with _reference_tracer.start_as_current_span(
            span_name,
            kind=SpanKind.SERVER,
            attributes=attributes,
            context=extract_trace_context(ctx.meta),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
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
                # Per mcp.server.status.attributes, caller errors (-32700, -32600,
                # -32601, -32602, -32002) are not server errors, while other codes are.
                if error.error.code not in (-32700, -32600, -32601, -32602, -32002):
                    span.set_attribute("error.type", code)
                    span.set_status(StatusCode.ERROR, error.error.message)
                raise
            except ValidationError:
                code = str(INVALID_PARAMS)
                span.set_attribute("rpc.response.status_code", code)
                raise
            except Exception as error:
                span.set_attribute("error.type", type(error).__qualname__)
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
                    span.set_status(StatusCode.ERROR)
                elif structured_content is not None:
                    span.set_attribute("gen_ai.tool.call.result", structured_content)
            return result


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


def _client_common_attributes(
    method: str,
    session: ClientSession,
    transport: StreamableHTTPTransport,
    host: str | None,
    port: int | None,
) -> dict[str, Any]:
    request_id = str(session._dispatcher._next_id)
    attributes: dict[str, Any] = {
        "mcp.method.name": method,
        "jsonrpc.request.id": request_id,
        "network.transport": "tcp",
        "network.protocol.name": "http",
        "network.protocol.version": "1.1",
    }
    if session._negotiated_version:
        attributes["mcp.protocol.version"] = session._negotiated_version
    if transport.session_id:
        attributes["mcp.session.id"] = transport.session_id
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


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
    span_attrs = _client_common_attributes("tools/call", session, transport, host, port)
    span_attrs["gen_ai.operation.name"] = "execute_tool"
    span_attrs["gen_ai.tool.name"] = tool_name

    with _reference_tracer.start_as_current_span(
        f"tools/call {tool_name}",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        span.set_attribute("gen_ai.tool.call.arguments", arguments)
        result = await session.call_tool(tool_name, arguments)
        if result.structured_content is not None:
            span.set_attribute("gen_ai.tool.call.result", result.structured_content)
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
    span_attrs = _client_common_attributes("prompts/get", session, transport, host, port)
    span_attrs["gen_ai.prompt.name"] = prompt_name

    with _reference_tracer.start_as_current_span(
        f"prompts/get {prompt_name}",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        span.set_attribute("gen_ai.prompt.variables", prompt_arguments)
        prompt_result = await session.get_prompt(prompt_name, prompt_arguments)
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
    span_attrs = _client_common_attributes("resources/read", session, transport, host, port)
    span_attrs["mcp.resource.uri"] = resource_uri

    with _reference_tracer.start_as_current_span(
        "resources/read",
        kind=SpanKind.CLIENT,
        attributes=span_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ):
        resource_result = await session.read_resource(resource_uri)
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
    span_attrs = _client_common_attributes("tools/call", session, transport, host, port)
    span_attrs["gen_ai.operation.name"] = "execute_tool"
    span_attrs["gen_ai.tool.name"] = tool_name

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
                span.set_status(StatusCode.ERROR)
                print("    -> CallToolResult isError=True (error.type=tool_error)")
        except MCPError as error:
            code = str(error.error.code)
            span.set_attribute("error.type", code)
            span.set_attribute("rpc.response.status_code", code)
            span.set_status(StatusCode.ERROR, error.error.message)

    missing_uri = "file:///weather/missing.json"
    res_attrs = _client_common_attributes("resources/read", session, transport, host, port)
    res_attrs["mcp.resource.uri"] = missing_uri
    with _reference_tracer.start_as_current_span(
        "resources/read",
        kind=SpanKind.CLIENT,
        attributes=res_attrs,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            await session.read_resource(missing_uri)
        except MCPError as error:
            code = str(error.error.code)
            span.set_attribute("error.type", code)
            span.set_attribute("rpc.response.status_code", code)
            span.set_status(StatusCode.ERROR, error.error.message)
            print(f"    -> JSON-RPC error {code}: {error.error.message}")


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
    asyncio.run(run_scenarios())
    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
