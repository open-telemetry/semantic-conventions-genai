"""Minimal remote A2A agent used by the Google ADK reference scenario."""

import argparse

import uvicorn
from a2a.helpers.proto_helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill, Part
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def health(_request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


class WeatherAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            if context.message is None:
                raise ValueError("A2A request must include a message")
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.add_artifact(
            [Part(text="Sunny, 72 degrees Fahrenheit")],
            name="weather",
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            raise ValueError("A2A cancellation must identify a task")
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.cancel()


def create_app(host: str, port: int) -> Starlette:
    rpc_url = "/a2a/jsonrpc"
    agent_card = AgentCard(
        name="weather-agent",
        description="Returns weather information for a requested location.",
        version="1.0.0",
        provider=AgentProvider(
            organization="example.weather",
            url=f"http://{host}:{port}",
        ),
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="weather",
                name="Weather",
                description="Returns weather information.",
                tags=["weather"],
            )
        ],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://{host}:{port}{rpc_url}",
            )
        ],
    )
    request_handler = DefaultRequestHandler(
        agent_executor=WeatherAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    routes = [
        Route("/health", health),
        *create_agent_card_routes(agent_card),
        *create_jsonrpc_routes(request_handler=request_handler, rpc_url=rpc_url),
    ]
    return Starlette(routes=routes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(create_app(args.host, args.port), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
