"""A2A + `gen_ai.main_agent` showcase driven by a real Google ADK agent.

This scenario only sets up the OTel pipeline and the process Resource
(`gen_ai.main_agent.*`, derived from env with fallback to the served AgentCard).
Everything else is a real Google ADK agent served over A2A via ``to_a2a`` and
invoked by an A2A client -- ADK's own instrumentation emits the spans.
"""

import asyncio
import os

import httpx
from a2a.client import A2AClient
from a2a.types import AgentCard, Message, MessageSendParams, Part, Role, SendMessageRequest, TextPart
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from opentelemetry.sdk.resources import Resource
from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

# Address the agent is served at; also the AgentCard `url`.
AGENT_HOST = "a2a-server"
AGENT_BASE_URL = f"http://{AGENT_HOST}"


def resolve_main_agent_id(card: AgentCard) -> str:
    """Prefer a hosting platform-injected id; otherwise fall back to the
    AgentCard url."""
    return os.environ.get("GEN_AI_MAIN_AGENT_ID") or card.url


def build_agent() -> Agent:
    return Agent(
        name="travel_assistant",
        model=Gemini(model="gemini-2.0-flash", base_url=MOCK_BASE_URL),
        instruction="You are a helpful travel planning assistant.",
        description="Top-level travel planning A2A agent service.",
    )


async def run():
    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")

    agent = build_agent()

    # The AgentCard is derived from the agent itself and the URL it will be served at;
    card = await AgentCardBuilder(agent=agent, rpc_url=f"{AGENT_BASE_URL}/").build()
    resource = Resource.create(
        {
            "gen_ai.main_agent.id": resolve_main_agent_id(card),
            "gen_ai.main_agent.name": card.name,
            "gen_ai.main_agent.description": card.description or "",
        }
    )
    tp, lp, mp = setup_otel(resource=resource)

    # Serve the real ADK agent over A2A and invoke it
    app = to_a2a(agent, agent_card=card, host=AGENT_HOST, port=80, protocol="http")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=AGENT_BASE_URL) as httpx_client,
    ):
        print("  [a2a_showcase] A2A client invoking the ADK agent over ASGI transport")
        client = A2AClient(httpx_client, agent_card=card)
        request = SendMessageRequest(
            id="req-1",
            params=MessageSendParams(
                message=Message(
                    role=Role.user,
                    message_id="msg-req-1",
                    parts=[Part(root=TextPart(text="Find me a flight to Seattle."))],
                )
            ),
        )
        response = await client.send_message(request)
        print(f"    -> {response.model_dump(exclude_none=True, mode='json').get('result', '')}"[:120])

    flush_and_shutdown(tp, lp, mp)


def main():
    print("=== A2A + gen_ai.main_agent showcase (real Google ADK agent) ===")
    asyncio.run(run())


if __name__ == "__main__":
    main()
