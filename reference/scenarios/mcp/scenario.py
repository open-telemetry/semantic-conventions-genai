"""Reference implementation for the MCP Python SDK (`mcp`).

The client below launches `server.py` -- an MCP server built with the same SDK --
over the stdio transport. Both processes record the MCP operation metrics with
`instrument_streams`, which observes every JSON-RPC message where the SDK hands
it to, or takes it from, the transport: the `SessionMessage` streams that
`stdio_client()` and `stdio_server()` return.
"""

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import anyio
from mcp import ClientSession, MCPError, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared import _otel as sdk_otel
from mcp.shared.message import SessionMessage
from opentelemetry import metrics, trace
from reference_shared import flush_and_shutdown, reference_meter, setup_otel

SERVER_SCRIPT = Path(__file__).with_name("server.py")

_meter = reference_meter()
# Bucket boundaries advised for the duration and size metrics by docs/gen-ai/mcp.md.
_DURATION_BUCKETS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]
_SIZE_BUCKETS = [64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216]


@dataclass(frozen=True)
class _Instruments:
    """The metrics of one side of an MCP operation."""

    duration: metrics.Histogram
    active: metrics.UpDownCounter
    request_size: metrics.Histogram
    response_size: metrics.Histogram
    # JSON-RPC error codes that do not make the operation fail on this side.
    non_error_codes: frozenset[int]


# Recorded by whoever sends the request or notification.
_CLIENT = _Instruments(
    duration=_meter.create_histogram(
        "mcp.client.operation.duration",
        unit="s",
        description="The duration of the MCP request or notification as observed on the sender "
        "from the time it was sent until the response or ack is received.",
        explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
    ),
    active=_meter.create_up_down_counter(
        "mcp.client.operation.active",
        unit="{operation}",
        description="The number of MCP requests and notifications in progress as observed on the sender.",
    ),
    request_size=_meter.create_histogram(
        "mcp.client.request.size",
        unit="By",
        description="The size of the MCP request or notification as observed on the sender.",
        explicit_bucket_boundaries_advisory=_SIZE_BUCKETS,
    ),
    response_size=_meter.create_histogram(
        "mcp.client.response.size",
        unit="By",
        description="The size of the MCP response as observed on the sender.",
        explicit_bucket_boundaries_advisory=_SIZE_BUCKETS,
    ),
    # Every error code the sender receives is an error.
    non_error_codes=frozenset(),
)

# Recorded by whoever receives the request or notification.
_SERVER = _Instruments(
    duration=_meter.create_histogram(
        "mcp.server.operation.duration",
        unit="s",
        description="MCP request or notification duration as observed on the receiver "
        "from the time it was received until the result or ack is sent.",
        explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
    ),
    active=_meter.create_up_down_counter(
        "mcp.server.operation.active",
        unit="{operation}",
        description="The number of MCP requests and notifications in progress as observed on the receiver.",
    ),
    request_size=_meter.create_histogram(
        "mcp.server.request.size",
        unit="By",
        description="The size of the MCP request or notification as observed on the receiver.",
        explicit_bucket_boundaries_advisory=_SIZE_BUCKETS,
    ),
    response_size=_meter.create_histogram(
        "mcp.server.response.size",
        unit="By",
        description="The size of the MCP response as observed on the receiver.",
        explicit_bucket_boundaries_advisory=_SIZE_BUCKETS,
    ),
    # The caller sent a request the receiver could not serve: parse error, invalid
    # request, method not found, invalid params (also an unknown tool), resource not found.
    non_error_codes=frozenset(
        {types.PARSE_ERROR, types.INVALID_REQUEST, types.METHOD_NOT_FOUND, types.INVALID_PARAMS, -32002}
    ),
)


def suppress_sdk_spans() -> None:
    """Drop the spans the SDK emits on its own `mcp-python-sdk` tracer.

    They would otherwise be validated alongside the metrics this scenario
    demonstrates; the server spans carry `gen_ai.operation.name=execute_tool`,
    so they would also be counted as GenAI `execute_tool` spans. The client
    spans have no public opt-out, so the tracer both sides share is replaced.
    """
    sdk_otel._tracer = trace.NoOpTracer()


def _message_size(message: types.JSONRPCMessage) -> int:
    """Size of the message as compact UTF-8 JSON, without the newline delimiter.

    For a sent message these are exactly the bytes the SDK's stdio transports
    write. A received message reaches this code already parsed, so this is the
    re-serialized size the conventions allow when the received bytes are not
    available.
    """
    return len(message.model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8"))


@dataclass
class _Operation:
    """A request or notification in progress."""

    instruments: _Instruments
    # Known when the operation starts; the active counter is updated with exactly these.
    attributes: dict[str, str]
    request_size: int
    # Opt-in on the duration and size metrics, which the active counter does not share.
    resource_uri: str | None = None
    start: float = field(default_factory=time.perf_counter)


class _MessageMetrics:
    """Records the MCP operation metrics of one connection from the JSON-RPC messages it carries.

    A request or notification this side sends is a client operation, one it
    receives a server operation -- an MCP server may send requests too.
    """

    def __init__(self, network_transport: str):
        self._network_transport = network_transport
        self._protocol_version: str | None = None
        self._sent: dict[types.RequestId, _Operation] = {}
        self._received: dict[types.RequestId, _Operation] = {}

    def _start(
        self, instruments: _Instruments, message: types.JSONRPCRequest | types.JSONRPCNotification, size: int
    ) -> _Operation:
        attributes = {"mcp.method.name": message.method, "network.transport": self._network_transport}
        if self._protocol_version is not None:
            attributes["mcp.protocol.version"] = self._protocol_version
        params = message.params or {}
        name, uri = params.get("name"), params.get("uri")
        if message.method == "tools/call":
            attributes["gen_ai.operation.name"] = "execute_tool"
            if isinstance(name, str):
                attributes["gen_ai.tool.name"] = name
        elif message.method == "prompts/get" and isinstance(name, str):
            attributes["gen_ai.prompt.name"] = name
        instruments.active.add(1, attributes)
        # Only the resource requests and notifications carry a top-level `uri`.
        return _Operation(instruments, attributes, size, resource_uri=uri if isinstance(uri, str) else None)

    def _end(
        self,
        operation: _Operation,
        response: types.JSONRPCMessage | None = None,
        size: int | None = None,
        error_type: str | None = None,
    ):
        instruments = operation.instruments
        duration = time.perf_counter() - operation.start
        instruments.active.add(-1, operation.attributes)
        attributes = dict(operation.attributes)
        if operation.resource_uri is not None:
            attributes["mcp.resource.uri"] = operation.resource_uri
        if isinstance(response, types.JSONRPCResponse) and attributes["mcp.method.name"] == "initialize":
            # The version the server picked; every later operation on this connection uses it.
            self._protocol_version = response.result["protocolVersion"]
            attributes["mcp.protocol.version"] = self._protocol_version
        elif isinstance(response, types.JSONRPCError):
            code = response.error.code
            attributes["rpc.response.status_code"] = str(code)
            if code not in instruments.non_error_codes:
                attributes["error.type"] = str(code)
        if error_type is not None:
            attributes["error.type"] = error_type
        instruments.duration.record(duration, attributes)
        instruments.request_size.record(operation.request_size, attributes)
        # Only an answered request has a response to measure.
        if size is not None:
            instruments.response_size.record(size, attributes)

    def _cancel(self, pending: dict[types.RequestId, _Operation], notification: types.JSONRPCNotification) -> None:
        """End the request a `notifications/cancelled` names: MCP never answers a cancelled request."""
        request_id = (notification.params or {}).get("requestId")
        if isinstance(request_id, int | str) and request_id in pending:
            self._end(pending.pop(request_id), error_type="cancelled")

    def close(self) -> None:
        """End every request the connection leaves unanswered."""
        for pending in (self._sent, self._received):
            while pending:
                # The code the SDK fails a pending request with when the connection closes.
                self._end(pending.popitem()[1], error_type=str(types.CONNECTION_CLOSED))

    async def send(self, write_stream, item: SessionMessage) -> None:
        """Hand `item` to the transport, recording the operation it starts or ends."""
        message = item.message
        size = _message_size(message)
        if isinstance(message, types.JSONRPCRequest):
            self._sent[message.id] = self._start(_CLIENT, message, size)
            await write_stream.send(item)
        elif isinstance(message, types.JSONRPCNotification):
            # Nothing acknowledges a notification on stdio: it is done once the transport has it.
            operation = self._start(_CLIENT, message, size)
            await write_stream.send(item)
            self._end(operation)
            if message.method == "notifications/cancelled":
                self._cancel(self._sent, message)
        else:
            await write_stream.send(item)
            if message.id in self._received:
                self._end(self._received.pop(message.id), message, size)

    def received(self, message: types.JSONRPCMessage) -> None:
        """Record the operation a message the transport delivered starts or ends."""
        size = _message_size(message)
        if isinstance(message, types.JSONRPCRequest):
            self._received[message.id] = self._start(_SERVER, message, size)
        elif isinstance(message, types.JSONRPCResponse | types.JSONRPCError) and message.id in self._sent:
            self._end(self._sent.pop(message.id), message, size)
        elif isinstance(message, types.JSONRPCNotification) and message.method == "notifications/cancelled":
            self._cancel(self._received, message)
        # Nothing acknowledges a received notification on stdio, and its processing
        # isn't visible from the transport, so the receiver does not record it.


class _ReadStream:
    def __init__(self, inner, recorder: _MessageMetrics):
        self._inner = inner
        self._recorder = recorder

    async def receive(self):
        try:
            item = await self._inner.receive()
        except anyio.EndOfStream:
            self._recorder.close()
            raise
        if isinstance(item, SessionMessage):
            self._recorder.received(item.message)
        return item

    @property
    def last_context(self):
        # The sender's contextvars, which the SDK reads off context-aware streams.
        return getattr(self._inner, "last_context", None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    async def aclose(self):
        self._recorder.close()
        await self._inner.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.aclose()


class _WriteStream:
    def __init__(self, inner, recorder: _MessageMetrics):
        self._inner = inner
        self._recorder = recorder

    async def send(self, item: SessionMessage):
        await self._recorder.send(self._inner, item)

    async def aclose(self):
        await self._inner.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.aclose()


def instrument_streams(read_stream, write_stream, *, network_transport: str):
    """Wrap a transport's `SessionMessage` streams to record the MCP operation metrics."""
    recorder = _MessageMetrics(network_transport)
    return _ReadStream(read_stream, recorder), _WriteStream(write_stream, recorder)


async def run_client():
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
        # stdio_client passes the server a minimal environment; it exports its own telemetry.
        env={"OTEL_EXPORTER_OTLP_ENDPOINT": os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]},
    )
    async with stdio_client(server) as (read_stream, write_stream):
        # stdio talks to the server over its stdin and stdout pipes.
        read_stream, write_stream = instrument_streams(read_stream, write_stream, network_transport="pipe")
        async with ClientSession(read_stream, write_stream) as session:
            print("  [initialize]")
            result = await session.initialize()
            print(f"    -> protocol version {result.protocol_version}")

            print("  [tools/list]")
            tools = await session.list_tools()
            print(f"    -> {[tool.name for tool in tools.tools]}")

            print("  [tools/call] get_weather")
            call = await session.call_tool("get_weather", {"city": "Paris"})
            print(f"    -> {call.content[0].text}")

            print("  [tools/call] unknown tool")
            try:
                await session.call_tool("get_forecast", {"city": "Paris"})
            except MCPError as error:
                print(f"    -> JSON-RPC error {error.code}: {error.message}")

            print("  [prompts/get] weather_report")
            prompt = await session.get_prompt("weather_report", {"city": "Paris"})
            print(f"    -> {prompt.messages[0].content.text}")

            print("  [resources/read] weather://paris")
            resource = await session.read_resource("weather://paris")
            print(f"    -> {resource.contents[0].text}")


def main():
    print("=== MCP Python SDK: stdio client and server ===")
    tp, lp, mp = setup_otel()
    suppress_sdk_spans()
    anyio.run(run_client)
    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
