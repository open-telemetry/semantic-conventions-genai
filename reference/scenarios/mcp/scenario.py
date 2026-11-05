"""Reference implementation for the MCP Python SDK: client and server spans over Streamable HTTP."""

import asyncio
import base64
import json
import socket
from contextvars import ContextVar
from urllib.parse import urlparse

import uvicorn
from mcp import Client, ClientSession, MCPError
from mcp.client.streamable_http import StreamableHTTPTransport
from mcp.server.mcpserver import MCPServer
from mcp.shared import _otel as mcp_native_otel
from mcp.types import INTERNAL_ERROR, CallToolResult, ImageContent, InitializeResult, TextContent
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

# JSON-RPC error codes that mean the caller sent a request the server could not
# serve. The server span does not count them as errors.
CALLER_ERROR_CODES = (-32700, -32600, -32601, -32602, -32002)

# A 1x1 PNG.
WEATHER_MAP_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

server = MCPServer("weather")


@server.tool()
def get_weather(location: str) -> dict[str, str | int]:
    """Get the current weather. The SDK returns it as structured content and repeats it in a text block."""
    return {"location": location, "temperature": 57}


@server.tool()
def get_weather_map(location: str) -> CallToolResult:
    """Get the current weather as structured content, with a map image."""
    weather = {"location": location, "temperature": 57}
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(weather)),
            ImageContent(type="image", data=base64.b64encode(WEATHER_MAP_PNG).decode(), mime_type="image/png"),
        ],
        structured_content=weather,
    )


@server.tool(structured_output=False)
def get_weather_summary(location: str) -> str:
    """Get the current weather as plain text."""
    return f"57 degrees and rainy in {location}"


@server.tool()
def get_weather_alerts(location: str) -> str:
    """Fail with a JSON-RPC error."""
    raise MCPError(code=INTERNAL_ERROR, message=f"No alert feed for {location}")


async def traced_server_request(ctx, call_next):
    """Server middleware: one span per inbound MCP message."""
    params = ctx.params or {}
    tool_name = params.get("name") if ctx.method == "tools/call" else None
    attributes = {"mcp.method.name": ctx.method, "mcp.protocol.version": ctx.protocol_version}
    if ctx.request_id is not None:
        attributes["jsonrpc.request.id"] = str(ctx.request_id)
    if tool_name:
        attributes["gen_ai.operation.name"] = "execute_tool"
        attributes["gen_ai.tool.name"] = tool_name
        attributes["gen_ai.tool.call.arguments"] = json.dumps(params.get("arguments") or {})
    if (http_request := ctx.request) is not None:
        attributes["network.transport"] = "tcp"
        attributes["network.protocol.name"] = "http"
        attributes["network.protocol.version"] = http_request.scope["http_version"]
        if peer := http_request.client:
            attributes["client.address"] = peer.host
            attributes["client.port"] = peer.port
        if session_id := http_request.headers.get("mcp-session-id"):
            attributes["mcp.session.id"] = session_id
    # The parent comes from params._meta; the transport's own context, if there is one, becomes a link.
    ambient = trace.get_current_span().get_span_context()
    with reference_tracer().start_as_current_span(
        f"{ctx.method} {tool_name}" if tool_name else ctx.method,
        context=propagate.extract(ctx.meta or {}),
        kind=SpanKind.SERVER,
        attributes=attributes,
        links=[trace.Link(ambient)] if ambient.is_valid else None,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            result = await call_next(ctx)
        except MCPError as error:
            span.set_attribute("rpc.response.status_code", str(error.code))
            if error.code not in CALLER_ERROR_CODES:
                span.set_attribute("error.type", str(error.code))
                span.set_status(StatusCode.ERROR, error.message)
            raise
        if tool_name:
            # MCPServer hands the middleware the result in its wire form.
            if result.get("isError"):
                span.set_attribute("error.type", "tool_error")
                span.set_status(StatusCode.ERROR)
                return result
            content = result.get("content", [])
            if result.get("structuredContent") is not None:
                span.set_attribute("gen_ai.tool.call.result", json.dumps(result["structuredContent"]))
            elif len(content) == 1 and content[0]["type"] == "text":
                try:
                    span.set_attribute("gen_ai.tool.call.result", json.dumps(json.loads(content[0]["text"])))
                except ValueError:
                    span.set_attribute("gen_ai.tool.call.result", content[0]["text"])
            elif content:
                span.set_attribute(
                    "gen_ai.tool.call.result",
                    json.dumps(
                        [
                            {"type": "text", "content": block["text"]}
                            if block["type"] == "text"
                            else {
                                "type": "blob",
                                "modality": "image",
                                "mime_type": block["mimeType"],
                                "content": block["data"],
                            }
                            for block in content
                        ]
                    ),
                )
        return result


original_send_request = ClientSession.send_request
client_span = ContextVar("client_span")


async def traced_send_request(session, request, *args, **kwargs):
    """Client session request dispatch: one span per outbound MCP request."""
    tool_name = request.params.name if request.method == "tools/call" else None
    with reference_tracer().start_as_current_span(
        f"{request.method} {tool_name}" if tool_name else request.method,
        kind=SpanKind.CLIENT,
        attributes={"mcp.method.name": request.method},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        client_span.set(span)
        if session.protocol_version:
            span.set_attribute("mcp.protocol.version", session.protocol_version)
        if tool_name:
            span.set_attribute("gen_ai.operation.name", "execute_tool")
            span.set_attribute("gen_ai.tool.name", tool_name)
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(request.params.arguments or {}))
        try:
            result = await original_send_request(session, request, *args, **kwargs)
        except MCPError as error:
            span.set_attribute("rpc.response.status_code", str(error.error.code))
            span.set_attribute("error.type", str(error.error.code))
            span.set_status(StatusCode.ERROR, error.error.message)
            raise
        if isinstance(result, InitializeResult):
            span.set_attribute("mcp.protocol.version", result.protocol_version)
        if isinstance(result, CallToolResult):
            if result.is_error:
                span.set_attribute("error.type", "tool_error")
                span.set_status(StatusCode.ERROR)
                return result
            if result.structured_content is not None:
                span.set_attribute("gen_ai.tool.call.result", json.dumps(result.structured_content))
            elif len(result.content) == 1 and result.content[0].type == "text":
                try:
                    span.set_attribute("gen_ai.tool.call.result", json.dumps(json.loads(result.content[0].text)))
                except ValueError:
                    span.set_attribute("gen_ai.tool.call.result", result.content[0].text)
            elif result.content:
                span.set_attribute(
                    "gen_ai.tool.call.result",
                    json.dumps(
                        [
                            {"type": "text", "content": block.text}
                            if block.type == "text"
                            else {
                                "type": "blob",
                                "modality": "image",
                                "mime_type": block.mime_type,
                                "content": block.data,
                            }
                            for block in result.content
                        ]
                    ),
                )
        return result


original_handle_post_request = StreamableHTTPTransport._handle_post_request


async def traced_handle_post_request(transport, ctx):
    """HTTP transport send. The SDK runs it in the sender's context, so it can reach the client span."""
    if (span := client_span.get(None)) and span.is_recording():
        url = urlparse(transport.url)
        span.set_attribute("jsonrpc.request.id", str(ctx.session_message.message.id))
        span.set_attribute("network.transport", "tcp")
        span.set_attribute("network.protocol.name", "http")
        span.set_attribute("server.address", url.hostname)
        span.set_attribute("server.port", url.port)
        if transport.session_id:
            span.set_attribute("mcp.session.id", transport.session_id)
    await original_handle_post_request(transport, ctx)


async def run_tool_calls():
    """Scenario: an MCP client calls tools on an MCP server over Streamable HTTP."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    http_server = uvicorn.Server(
        uvicorn.Config(server.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    serving = asyncio.create_task(http_server.serve())
    while not http_server.started:
        await asyncio.sleep(0.05)
    try:
        # "legacy" is the initialize handshake of protocol version 2025-11-25, which has sessions.
        async with Client(f"http://127.0.0.1:{port}/mcp", mode="legacy") as client:
            # The server has no get_tides tool; the SDK answers with a tool error.
            for tool_name in ("get_weather", "get_weather_map", "get_weather_summary", "get_tides"):
                print(f"  [tools/call] {tool_name}")
                result = await client.call_tool(tool_name, {"location": "Seattle"})
                print(f"    -> {[block.type for block in result.content]}, error={result.is_error}")
            print("  [tools/call] get_weather_alerts")
            try:
                await client.call_tool("get_weather_alerts", {"location": "Seattle"})
            except MCPError as error:
                print(f"    -> JSON-RPC error {error.error.code}")
    finally:
        http_server.should_exit = True
        await serving


def main():
    print("=== Reference Implementation: MCP Python SDK ===")

    tp, lp, mp = setup_otel()

    # The SDK emits its own spans; the reference spans replace them.
    mcp_native_otel._tracer = trace.NoOpTracer()
    server.middleware[:] = [traced_server_request]
    ClientSession.send_request = traced_send_request
    StreamableHTTPTransport._handle_post_request = traced_handle_post_request
    try:
        asyncio.run(run_tool_calls())
    finally:
        ClientSession.send_request = original_send_request
        StreamableHTTPTransport._handle_post_request = original_handle_post_request

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
