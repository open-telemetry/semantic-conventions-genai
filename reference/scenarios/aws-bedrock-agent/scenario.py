"""Reference implementation: AWS Bedrock Agent create_agent / invoke_agent with manual instrumentation.

Exercises: create_agent (Bedrock Agent CreateAgent API) and invoke_agent
(Bedrock Agent Runtime InvokeAgent API) against a mock Bedrock server, with
manual span instrumentation.
"""

import json
import os
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlparse

import boto3
from botocore.awsrequest import AWSResponse
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel
from urllib3.response import HTTPResponse

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
_parsed = urlparse(MOCK_BASE_URL)
_SERVER_ADDRESS = _parsed.hostname or "localhost"
_SERVER_PORT = _parsed.port or 443

tracer = reference_tracer("gen_ai.client.aws_bedrock")

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
    with tracer.start_as_current_span(
        "invoke_agent", kind=SpanKind.CLIENT, attributes=span_attributes, record_exception=False
    ) as span:
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
            input_tokens = []
            output_tokens = []
            for event in response["completion"]:
                if "chunk" in event:
                    text += event["chunk"].get("bytes", b"").decode("utf-8")
                elif "trace" in event:
                    trace = event["trace"].get("trace", {})
                    for trace_type in ("preProcessingTrace", "orchestrationTrace", "postProcessingTrace"):
                        model_output = trace.get(trace_type, {}).get("modelInvocationOutput", {})
                        usage = model_output.get("metadata", {}).get("usage", {})
                        if usage.get("inputTokens") is not None:
                            input_tokens.append(usage["inputTokens"])
                        if usage.get("outputTokens") is not None:
                            output_tokens.append(usage["outputTokens"])
                    agent_version = event["trace"].get("agentVersion")
                    if agent_version:
                        span.set_attribute("gen_ai.agent.version", agent_version)
            if input_tokens:
                span.set_attribute("gen_ai.usage.input_tokens", sum(input_tokens))
            if output_tokens:
                span.set_attribute("gen_ai.usage.output_tokens", sum(output_tokens))
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
        except Exception as error:
            span.set_status(StatusCode.ERROR, str(error))
            span.set_attribute("error.type", f"{type(error).__module__}.{type(error).__qualname__}")
            reference_event_logger().emit(
                event_name="gen_ai.client.invoke_agent.exception",
                severity_number=SeverityNumber.WARN,
                exception=error,
            )
            raise


def run_invoke_agent_error(client, agent_id):
    """Exercise an invoke-agent exception raised by the SDK for an invalid request."""
    response = AWSResponse(
        url=f"{MOCK_BASE_URL}/agents/{agent_id}/agentAliases/{AGENT_ALIAS_ID}/sessions/{SESSION_ID}/text",
        status_code=400,
        headers={"content-type": "application/json", "x-amzn-errortype": "ValidationException"},
        raw=HTTPResponse(
            body=BytesIO(json.dumps({"message": "Invalid agent alias"}).encode("utf-8")),
            preload_content=False,
        ),
    )
    with patch.object(client._endpoint.http_session, "send", return_value=response):
        try:
            run_invoke_agent(client, agent_id)
        except client.exceptions.ValidationException as error:
            print(f"    -> expected SDK error: {error}")
        else:
            raise AssertionError("Expected the SDK to reject the agent invocation request")


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
    run_invoke_agent_error(runtime_client, agent_id)

    flush_and_shutdown(tp, lp, mp)
