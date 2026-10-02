"""Reference implementation for Microsoft Foundry Agent Service."""

import json
import os
from urllib.parse import urlparse, urlunparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.credentials import AccessToken
from azure.core.pipeline.policies import SansIOHTTPPolicy
from openai import DefaultHttpxClient
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
FOUNDRY_PROJECT_ENDPOINT = "https://foundry-resource.services.ai.azure.com/api/projects/reference-project"
_project_endpoint = urlparse(FOUNDRY_PROJECT_ENDPOINT)
_SERVER_ADDRESS = _project_endpoint.hostname
_SERVER_PORT = _project_endpoint.port

tracer = trace.get_tracer("gen_ai.client.azure_ai_foundry")

AGENT_MODEL = "gpt-4o-mini"
AGENT_NAME = "refimpl-test-agent"
AGENT_DESCRIPTION = "Reference agent for the Azure AI Foundry Agents API flow."
AGENT_INSTRUCTIONS = "You are a helpful assistant."
USER_INPUT = "Hello, agent!"


def _route_agent_request_to_mock(request):
    logical_base_url = urlparse(f"{FOUNDRY_PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai")
    request_url = urlparse(str(request.url))
    logical_path = logical_base_url.path.rstrip("/")
    if request_url.netloc != logical_base_url.netloc or not request_url.path.startswith(logical_path):
        raise ValueError(f"unexpected Foundry agent request URL: {request.url}")

    request_path = request_url.path.removeprefix(logical_path)
    if request.method == "POST" and request_path == "/conversations":
        mock_path = "/v1/threads"
    elif request.method == "DELETE" and request_path.startswith("/conversations/"):
        conversation_id = request_path.removeprefix("/conversations/")
        mock_path = f"/v1/assistants/{conversation_id}"
    elif request.method == "POST" and request_path == "/responses":
        mock_path = "/v1/responses"
    else:
        raise ValueError(f"unexpected Foundry agent request: {request.method} {request_path}")

    mock_url = urlparse(MOCK_BASE_URL)
    request.url = request.url.copy_with(
        scheme=mock_url.scheme,
        host=mock_url.hostname,
        port=mock_url.port,
        path=f"{mock_url.path.rstrip('/')}{mock_path}",
    )
    request.headers["host"] = request.url.netloc.decode("ascii")


class MockTransportPolicy(SansIOHTTPPolicy):
    """Route Azure SDK requests to the conformance mock server."""

    def on_request(self, request):
        request_url = urlparse(request.http_request.url)
        logical_path = _project_endpoint.path.rstrip("/")
        if request_url.netloc != _project_endpoint.netloc or not request_url.path.startswith(logical_path):
            raise ValueError(f"unexpected Foundry project request URL: {request.http_request.url}")

        mock_url = urlparse(MOCK_BASE_URL)
        mock_path = f"{mock_url.path.rstrip('/')}{request_url.path.removeprefix(logical_path)}"
        request.http_request.url = urlunparse(
            request_url._replace(
                scheme=mock_url.scheme,
                netloc=mock_url.netloc,
                path=mock_path,
            )
        )
        request.http_request.headers["Host"] = mock_url.netloc


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
        "gen_ai.provider.name": "azure.ai.foundry",
        "gen_ai.request.model": AGENT_MODEL,
        "gen_ai.agent.name": AGENT_NAME,
        "server.address": _SERVER_ADDRESS,
    }
    if _SERVER_PORT is not None and _SERVER_PORT != 443:
        span_attributes["server.port"] = _SERVER_PORT
    with tracer.start_as_current_span(
        f"create_agent {AGENT_NAME}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        try:
            span.set_attribute("gen_ai.agent.description", AGENT_DESCRIPTION)
            span.set_attribute(
                "gen_ai.system_instructions",
                json.dumps([{"type": "text", "content": AGENT_INSTRUCTIONS}]),
            )
            span.set_attribute(
                "gen_ai.tool.definitions",
                json.dumps(
                    [
                        {
                            "type": tool["type"],
                            "name": tool["function"]["name"],
                            "description": tool["function"]["description"],
                            "parameters": tool["function"]["parameters"],
                        }
                        for tool in tool_defs
                    ]
                ),
            )
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
        except Exception as error:
            span.set_attribute("error.type", type(error).__qualname__)
            raise

    openai_client = None
    owned_openai_http_client = None
    conversation = None
    primary_error = None
    try:
        owned_openai_http_client = DefaultHttpxClient(event_hooks={"request": [_route_agent_request_to_mock]})
        openai_client = client.get_openai_client(
            agent_name=agent.name,
            http_client=owned_openai_http_client,
        )
        owned_openai_http_client = None
        conversation = openai_client.conversations.create()
        span_attributes_2 = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.provider.name": "azure.ai.foundry",
            "gen_ai.agent.name": agent.name,
            "gen_ai.conversation.id": conversation.id,
            "server.address": _SERVER_ADDRESS,
        }
        if _SERVER_PORT is not None and _SERVER_PORT != 443:
            span_attributes_2["server.port"] = _SERVER_PORT
        with tracer.start_as_current_span(
            f"invoke_agent {agent.name}",
            kind=SpanKind.CLIENT,
            attributes=span_attributes_2,
        ) as span:
            try:
                response = openai_client.responses.create(
                    conversation=conversation.id,
                    input=USER_INPUT,
                )

                response_text = response.output_text
                if response_text:
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
            except Exception as error:
                span.set_attribute("error.type", type(error).__qualname__)
                span.set_status(StatusCode.ERROR, str(error))
                raise
    except BaseException as error:  # noqa: BLE001
        primary_error = error
    finally:
        # Continue cleanup so every failure can be reported with the primary error.
        cleanup_errors = []
        if conversation is not None:
            try:
                openai_client.conversations.delete(conversation_id=conversation.id)
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(error)
        if openai_client is not None:
            try:
                openai_client.close()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(error)
        if owned_openai_http_client is not None:
            try:
                owned_openai_http_client.close()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(error)
        try:
            client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        except BaseException as error:  # noqa: BLE001
            cleanup_errors.append(error)

        if primary_error is not None and cleanup_errors:
            raise BaseExceptionGroup(
                "Foundry agent invocation and cleanup failed",
                [primary_error, *cleanup_errors],
            ) from None
        if len(cleanup_errors) == 1:
            raise cleanup_errors[0]
        if cleanup_errors:
            raise BaseExceptionGroup("Foundry agent cleanup failed", cleanup_errors)

    if primary_error is not None:
        raise primary_error


if __name__ == "__main__":
    print("=== Manual: Azure AI Foundry Invoke Agent Reference Implementation ===")
    tp, lp, mp = setup_otel()

    client = None
    primary_error = None
    try:
        client = AIProjectClient(
            endpoint=FOUNDRY_PROJECT_ENDPOINT,
            credential=MockCredential(),
            authentication_policy=SansIOHTTPPolicy(),
            per_call_policies=[MockTransportPolicy()],
        )
        run_invoke_agent(client)
    except BaseException as error:  # noqa: BLE001
        primary_error = error

    cleanup_errors = []
    if client is not None:
        try:
            client.close()
        except BaseException as error:  # noqa: BLE001
            cleanup_errors.append(error)
    try:
        flush_and_shutdown(tp, lp, mp)
    except BaseException as error:  # noqa: BLE001
        cleanup_errors.append(error)

    if primary_error is not None and cleanup_errors:
        raise BaseExceptionGroup(
            "Foundry scenario and cleanup failed",
            [primary_error, *cleanup_errors],
        ) from None
    if len(cleanup_errors) == 1:
        raise cleanup_errors[0]
    if cleanup_errors:
        raise BaseExceptionGroup("Foundry scenario cleanup failed", cleanup_errors)
    if primary_error is not None:
        raise primary_error
