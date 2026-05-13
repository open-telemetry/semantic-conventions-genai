"""Reference implementation: Azure AI Foundry invoke_agent with manual instrumentation.

Exercises: invoke_agent (Azure AI Foundry Agents API: create agent, create
thread, run, poll) against a mock Azure AI Foundry server, with manual span
instrumentation.
"""

import json
import os
from urllib.parse import urlparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.credentials import AccessToken
from azure.core.pipeline.policies import SansIOHTTPPolicy
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
_parsed = urlparse(MOCK_BASE_URL)
_SERVER_ADDRESS = _parsed.hostname or "localhost"
_SERVER_PORT = _parsed.port or 443

tracer = trace.get_tracer("gen_ai.client.azure_ai_foundry")

AGENT_MODEL = "gpt-4o-mini"
AGENT_NAME = "refimpl-test-agent"
AGENT_DESCRIPTION = "Reference agent for the Azure AI Foundry Agents API flow."
AGENT_INSTRUCTIONS = "You are a helpful assistant."
USER_INPUT = "Hello, agent!"
REQUEST_MAX_TOKENS = 128
REQUEST_TEMPERATURE = 0.2
REQUEST_TOP_P = 0.9


class MockCredential:
    """Dummy TokenCredential for testing against the mock server."""

    def get_token(self, *scopes, **kwargs):
        return AccessToken("mock-token", 9999999999)


def run_invoke_agent(client):
    """Exercise Azure AI Foundry Agents API with manual OTel spans.

    Creates a CLIENT span with gen_ai invoke_agent attributes to demonstrate
    what an instrumentation library should capture for the Azure AI Foundry v2
    agent flow (create agent version, invoke through Responses API, get
    result).
    """
    print("  [invoke_agent] Azure AI Foundry Agents: create + run")

    tool_defs = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    # Create agent version using the v2 AIProjectClient surface.
    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": AGENT_MODEL,
        "gen_ai.agent.name": AGENT_NAME,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span("create_agent", kind=SpanKind.CLIENT, attributes=span_attributes) as span:
        span.set_attribute("gen_ai.agent.description", AGENT_DESCRIPTION)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": AGENT_INSTRUCTIONS}]))
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
        agent = client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=AGENT_MODEL,
                instructions=AGENT_INSTRUCTIONS,
                tools=tool_defs,
            ),
            description=AGENT_DESCRIPTION,
        )
        span.set_attribute("gen_ai.agent.id", agent.id)
        if getattr(agent, "version", None):
            span.set_attribute("gen_ai.agent.version", str(agent.version))

    # Invoke the agent through the Responses API, wrapped in a manual span.
    openai_client = client.get_openai_client()

    span_attributes_2 = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": AGENT_MODEL,
        "gen_ai.agent.name": agent.name,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span("invoke_agent", kind=SpanKind.CLIENT, attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.request.max_tokens", REQUEST_MAX_TOKENS)
        span.set_attribute("gen_ai.request.temperature", REQUEST_TEMPERATURE)
        span.set_attribute("gen_ai.request.top_p", REQUEST_TOP_P)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": AGENT_INSTRUCTIONS}]))
        span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": USER_INPUT}]}])
        )
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
        try:
            response = openai_client.responses.create(
                model=AGENT_MODEL,
                instructions=AGENT_INSTRUCTIONS,
                tools=tool_defs,
                input=USER_INPUT,
                max_output_tokens=REQUEST_MAX_TOKENS,
                temperature=REQUEST_TEMPERATURE,
                top_p=REQUEST_TOP_P,
                extra_body={
                    "agent_reference": {
                        "name": agent.name,
                        "type": "agent_reference",
                    }
                },
            )

            if getattr(response, "assistant_id", None):
                span.set_attribute("gen_ai.agent.id", response.assistant_id)

            response_text = None
            for output in getattr(response, "output", []) or []:
                if getattr(output, "type", None) != "message":
                    continue
                for content in getattr(output, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        response_text = getattr(content, "text", None)
                        break
                if response_text:
                    break

            if response_text:
                span.set_attribute("gen_ai.output.type", "text")
                span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": response_text}],
                            }
                        ]
                    ),
                )

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

            print(f"    -> {response_text or response.id}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise
        finally:
            openai_client.close()

    # Clean up
    client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)


if __name__ == "__main__":
    print("=== Manual: Azure AI Foundry Invoke Agent Reference Implementation ===")
    tp, lp, mp = setup_otel()

    client = AIProjectClient(
        endpoint=MOCK_BASE_URL,
        credential=MockCredential(),
        authentication_policy=SansIOHTTPPolicy(),
    )

    run_invoke_agent(client)

    flush_and_shutdown(tp, lp, mp)
