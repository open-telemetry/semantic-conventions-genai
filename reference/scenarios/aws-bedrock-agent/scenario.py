"""Reference implementation: AWS Bedrock Agent create_agent / invoke_agent with manual instrumentation.

Exercises: create_agent (Bedrock Agent CreateAgent API) and invoke_agent
(Bedrock Agent Runtime InvokeAgent API) against a mock Bedrock server, with
manual span instrumentation.
"""

import json
import os
from urllib.parse import urlparse

import boto3
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
_parsed = urlparse(MOCK_BASE_URL)
_SERVER_ADDRESS = _parsed.hostname or "localhost"
_SERVER_PORT = _parsed.port or 443

tracer = trace.get_tracer("gen_ai.client.aws_bedrock")

AGENT_ALIAS_ID = "MOCK_ALIAS_ID"
SESSION_ID = "mock-session-001"
USER_INPUT = "Hello, agent!"


def run_create_agent(client):
    """Exercise Bedrock Agent CreateAgent with manual OTel spans.

    Creates a CLIENT span with gen_ai create_agent attributes to demonstrate
    what an instrumentation library should capture. Returns the new agent id.
    """
    print("  [create_agent] Bedrock Agent CreateAgent")
    agent_name = "reference-agent"
    agent_description = "Reference Bedrock agent."
    agent_instruction = "You are a helpful assistant. Answer the user's questions accurately and concisely."
    foundation_model = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.request.model": foundation_model,
        "gen_ai.agent.name": agent_name,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span(
        f"create_agent {agent_name}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.agent.description", agent_description)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": agent_instruction}]))
        try:
            agent = client.create_agent(
                agentName=agent_name,
                description=agent_description,
                instruction=agent_instruction,
                foundationModel=foundation_model,
            )["agent"]
            span.set_attribute("gen_ai.agent.id", agent["agentId"])
            span.set_attribute("gen_ai.agent.version", agent["agentVersion"])
            print(f"    -> {agent['agentId']}")
            return agent["agentId"]
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def run_invoke_agent(client, agent_id):
    """Exercise Bedrock Agent Runtime InvokeAgent with manual OTel spans.

    Creates a CLIENT span with gen_ai invoke_agent attributes to demonstrate
    what an instrumentation library should capture.
    """
    print("  [invoke_agent] Bedrock Agent Runtime InvokeAgent")
    span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "aws.bedrock",
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span("invoke_agent", kind=SpanKind.CLIENT, attributes=span_attributes) as span:
        span.set_attribute("gen_ai.agent.id", agent_id)
        span.set_attribute("gen_ai.conversation.id", SESSION_ID)
        span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": USER_INPUT}]}])
        )
        try:
            response = client.invoke_agent(
                agentId=agent_id,
                agentAliasId=AGENT_ALIAS_ID,
                sessionId=SESSION_ID,
                inputText=USER_INPUT,
                enableTrace=True,
            )
            # Consume the event stream
            text = ""
            for event in response["completion"]:
                if "chunk" in event:
                    text += event["chunk"].get("bytes", b"").decode("utf-8")
                elif "trace" in event:
                    agent_version = event["trace"].get("agentVersion")
                    if agent_version:
                        span.set_attribute("gen_ai.agent.version", agent_version)
            if text:
                span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": text}],
                            }
                        ]
                    ),
                )
            print(f"    -> {text[:60]}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


if __name__ == "__main__":
    print("=== Manual: AWS Bedrock Agent Reference Implementation ===")
    tp, lp, mp = setup_otel()

    control_client = boto3.client(
        "bedrock-agent",
        endpoint_url=MOCK_BASE_URL,
        region_name="us-east-1",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )
    runtime_client = boto3.client(
        "bedrock-agent-runtime",
        endpoint_url=MOCK_BASE_URL,
        region_name="us-east-1",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )

    agent_id = run_create_agent(control_client)
    run_invoke_agent(runtime_client, agent_id)

    flush_and_shutdown(tp, lp, mp)
