"""Reference implementation: Azure AI Foundry invoke_agent with manual instrumentation.

Exercises: create_agent and invoke_agent (Azure AI Foundry Agents API, invoked
through the Responses API), including a failed invocation, against a mock
Azure AI Foundry server, with manual span instrumentation.
"""

import json
import os
import time
from urllib.parse import urlparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.credentials import AccessToken
from azure.core.pipeline.policies import SansIOHTTPPolicy
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_meter, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
_parsed = urlparse(MOCK_BASE_URL)
_SERVER_ADDRESS = _parsed.hostname or "localhost"
_SERVER_PORT = _parsed.port or 443

tracer = trace.get_tracer("gen_ai.client.azure_ai_foundry")
_reference_meter = reference_meter()

_invoke_agent_duration = _reference_meter.create_histogram(
    "gen_ai.client.invoke_agent.duration",
    unit="s",
    description="GenAI client invoke agent operation duration.",
    explicit_bucket_boundaries_advisory=[
        0.01,
        0.02,
        0.04,
        0.08,
        0.16,
        0.32,
        0.64,
        1.28,
        2.56,
        5.12,
        10.24,
        20.48,
        40.96,
        81.92,
    ],
)

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


TOOL_DEFS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current weather",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    }
]


def run_create_agent(client):
    """Create an agent version using the v2 AIProjectClient surface."""
    print("  [create_agent] Azure AI Foundry Agents: create")
    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": AGENT_MODEL,
        "gen_ai.agent.name": AGENT_NAME,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span(
        f"create_agent {AGENT_NAME}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.agent.description", AGENT_DESCRIPTION)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": AGENT_INSTRUCTIONS}]))
        span.set_attribute("gen_ai.tool.definitions", json.dumps(TOOL_DEFS))
        agent = client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=AGENT_MODEL,
                instructions=AGENT_INSTRUCTIONS,
                tools=TOOL_DEFS,
            ),
            description=AGENT_DESCRIPTION,
        )
        span.set_attribute("gen_ai.agent.id", agent.id)
        if getattr(agent, "version", None):
            span.set_attribute("gen_ai.agent.version", str(agent.version))
    return agent


def run_invoke_agent(openai_client, agent):
    """Invoke the agent through the Responses API, wrapped in a manual span."""
    print("  [invoke_agent] Azure AI Foundry Agents: run")
    span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": AGENT_MODEL,
        "gen_ai.agent.name": agent.name,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    metric_attributes = dict(span_attributes)
    start_time = time.perf_counter()
    with tracer.start_as_current_span(
        f"invoke_agent {agent.name}",
        kind=SpanKind.CLIENT,
        attributes=span_attributes,
        record_exception=False,
    ) as span:
        span.set_attribute("gen_ai.request.max_tokens", REQUEST_MAX_TOKENS)
        span.set_attribute("gen_ai.request.temperature", REQUEST_TEMPERATURE)
        span.set_attribute("gen_ai.request.top_p", REQUEST_TOP_P)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": AGENT_INSTRUCTIONS}]))
        span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": USER_INPUT}]}])
        )
        span.set_attribute("gen_ai.tool.definitions", json.dumps(TOOL_DEFS))
        try:
            response = openai_client.responses.create(
                model=AGENT_MODEL,
                instructions=AGENT_INSTRUCTIONS,
                tools=TOOL_DEFS,
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
            for output in response.output or []:
                if output.type != "message":
                    continue
                for content in output.content or []:
                    if content.type == "output_text":
                        response_text = content.text
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

            finish_reason = None
            if response.status == "completed":
                finish_reason = "stop"
            elif response.status == "incomplete":
                reason = response.incomplete_details.reason if response.incomplete_details else None
                finish_reason = {"max_output_tokens": "length", "content_filter": "content_filter"}.get(
                    reason, "incomplete"
                )
            elif response.status in ("failed", "cancelled"):
                finish_reason = "error"
            if finish_reason is not None:
                span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

            print(f"    -> {response_text or response.id}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes["error.type"] = type(e).__qualname__
            raise
        finally:
            _invoke_agent_duration.record(time.perf_counter() - start_time, metric_attributes)


def run_invoke_agent_error(client, agent):
    """Exercise an invoke_agent error returned through the SDK's HTTP transport."""
    import httpx2
    import openai

    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(
            400,
            json={"error": {"message": "Invalid input", "type": "invalid_request_error", "code": "invalid_input"}},
        )
    )
    with client.get_openai_client(http_client=httpx2.Client(transport=transport), max_retries=0) as openai_client:
        try:
            run_invoke_agent(openai_client, agent)
        except openai.BadRequestError:
            pass
        else:
            raise AssertionError("Expected the SDK to reject the invoke_agent request")


if __name__ == "__main__":
    print("=== Manual: Azure AI Foundry Invoke Agent Reference Implementation ===")
    tp, lp, mp = setup_otel()

    client = AIProjectClient(
        endpoint=MOCK_BASE_URL,
        credential=MockCredential(),
        authentication_policy=SansIOHTTPPolicy(),
    )

    agent = run_create_agent(client)
    with client.get_openai_client() as openai_client:
        run_invoke_agent(openai_client, agent)
    run_invoke_agent_error(client, agent)
    client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)

    flush_and_shutdown(tp, lp, mp)
