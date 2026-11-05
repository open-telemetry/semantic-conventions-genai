"""The A2A agent that the reference scenario serves and calls.

Only agent-side plumbing lives here -- the Agent Card, the executor, and the
`a2a-sdk` request handler that drives it. The `a2a.server` span is emitted in
`scenario.py`, at the SDK dispatch point the request arrives on.
"""

from __future__ import annotations

from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandlerV2, RequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
)
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol


def agent_card(url: str, *, tenant: str) -> AgentCard:
    """The card this agent publishes, and the one its own spans are read from."""
    return AgentCard(
        name="calendar-agent",
        description="Summarizes and tracks calendar tasks.",
        version="1.2.0",
        supported_interfaces=[
            AgentInterface(
                url=url,
                protocol_binding=TransportProtocol.JSONRPC,
                protocol_version=PROTOCOL_VERSION_1_0,
                tenant=tenant,
            )
        ],
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="summarize-calendar",
                name="Summarize calendar",
                description="Summarizes the upcoming calendar.",
                tags=["calendar"],
            )
        ],
    )


class CalendarAgentExecutor(AgentExecutor):
    """Submits the task, works it, publishes an artifact, then completes."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        await updater.add_artifact(
            [Part(text=f"Calendar summary for: {context.get_user_input()}")],
            name="calendar-summary",
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()


def request_handler(card: AgentCard) -> RequestHandler:
    return DefaultRequestHandlerV2(
        agent_executor=CalendarAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
