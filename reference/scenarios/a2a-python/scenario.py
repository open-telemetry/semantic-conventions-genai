"""Reference implementation for A2A Python SDK."""

import asyncio

import httpx
from a2a import types as a2a_types
from a2a.client import ClientConfig, create_client, minimal_agent_card
from a2a.utils.constants import TransportProtocol
from mock_server import running_mock_server
from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

PROTOCOL_VERSION = "1.0"
TENANT = "billing"
AGENT_NAME = "Weather Agent"
AGENT_DESCRIPTION = "Provides weather forecasts."
AGENT_VERSION = "1.0.0"

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


def _agent_card(a2a_url: str) -> a2a_types.AgentCard:
    card = minimal_agent_card(a2a_url, [TransportProtocol.JSONRPC])
    card.capabilities.streaming = True
    interface = next(
        interface for interface in card.supported_interfaces if interface.protocol_binding == TransportProtocol.JSONRPC
    )
    interface.tenant = TENANT
    interface.protocol_version = PROTOCOL_VERSION
    card.name = AGENT_NAME
    card.description = AGENT_DESCRIPTION
    card.version = AGENT_VERSION
    return card


async def _create_a2a_client(card: a2a_types.AgentCard, *, streaming: bool):
    httpx_client = httpx.AsyncClient()
    return await create_client(
        card,
        ClientConfig(streaming=streaming, httpx_client=httpx_client),
    )


async def run_message_send_reference(a2a_url: str) -> None:
    """Scenario: A2A JSON-RPC send_message with a task response."""
    print("  [send_message] A2A JSON-RPC send_message")
    method = "SendMessage"
    reference_task_ids = ["task-calendar-summary"]
    request = a2a_types.SendMessageRequest(
        tenant=TENANT,
        message=_message(
            "Summarize my calendar.",
            message_id="msg-user-1",
            reference_task_ids=reference_task_ids,
        ),
    )

    card = _agent_card(a2a_url)
    interface = next(
        interface for interface in card.supported_interfaces if interface.protocol_binding == TransportProtocol.JSONRPC
    )
    host, port = mock_server_host_port(a2a_url)
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


async def run_message_stream_reference(a2a_url: str) -> None:
    """Scenario: A2A JSON-RPC send_streaming_message with SSE task status events."""
    print("  [send_streaming_message] A2A JSON-RPC send_streaming_message")
    method = "SendStreamingMessage"
    request = a2a_types.SendMessageRequest(
        tenant=TENANT,
        message=_message(
            "Track this task.",
            message_id="msg-user-2",
        ),
    )

    event_count = 0
    task_id = None
    context_id = None
    task_state = None
    card = _agent_card(a2a_url)
    interface = next(
        interface for interface in card.supported_interfaces if interface.protocol_binding == TransportProtocol.JSONRPC
    )
    host, port = mock_server_host_port(a2a_url)
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


async def run_tasks_get_reference(a2a_url: str) -> None:
    """Scenario: A2A JSON-RPC get_task."""
    print("  [get_task] A2A JSON-RPC get_task")
    method = "GetTask"
    request = a2a_types.GetTaskRequest(
        tenant=TENANT,
        id="task-calendar-summary",
    )

    card = _agent_card(a2a_url)
    interface = next(
        interface for interface in card.supported_interfaces if interface.protocol_binding == TransportProtocol.JSONRPC
    )
    host, port = mock_server_host_port(a2a_url)
    span_attrs = {
        "a2a.method.name": method,
        "a2a.protocol.version": interface.protocol_version,
        "a2a.tenant": request.tenant,
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
        span.set_attribute("a2a.task.id", task.id)
        span.set_attribute("a2a.task.state", task_state)
        span.set_attribute("gen_ai.conversation.id", task.context_id)
    print(f"    -> {request.id} {task_state}")


async def run_scenarios(a2a_url: str) -> None:
    await run_message_send_reference(a2a_url)
    await run_message_stream_reference(a2a_url)
    await run_tasks_get_reference(a2a_url)


def main() -> None:
    print("=== Reference Implementation: A2A Python SDK ===")

    tp, lp, mp = setup_otel()

    with running_mock_server(
        tracer=_reference_tracer,
        span_kind=SpanKind.SERVER,
        agent_card_factory=_agent_card,
    ) as a2a_url:
        asyncio.run(run_scenarios(a2a_url))

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
