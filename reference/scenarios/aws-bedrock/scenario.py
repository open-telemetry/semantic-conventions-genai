"""Reference implementation for AWS Bedrock."""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()


def create_bedrock_client():
    """Create a boto3 Bedrock Runtime client pointing at the mock server."""
    import boto3

    return boto3.client(
        "bedrock-runtime",
        endpoint_url=MOCK_BASE_URL,
        region_name="us-east-1",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )


def run_converse_reference(client):
    """Scenario: Bedrock Converse API with reference implementation."""
    print("  [converse] Bedrock Converse API (reference implementation)")
    request_model = "anthropic.claude-3-haiku-20240307-v1:0"
    messages = [
        {
            "role": "user",
            "content": [{"text": "Say hello."}],
        }
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "chat anthropic.claude-3-haiku-20240307-v1:0", attributes=span_attributes
    ) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"][0]["text"]}]} for m in messages]
            ),
        )
        response = client.converse(
            modelId=request_model,
            messages=messages,
        )
        stop_reason = response.get("stopReason")
        if stop_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [stop_reason])
        usage = response.get("usage", {})
        if usage.get("inputTokens") is not None:
            span.set_attribute("gen_ai.usage.input_tokens", usage["inputTokens"])
        if usage.get("outputTokens") is not None:
            span.set_attribute("gen_ai.usage.output_tokens", usage["outputTokens"])
        text = response["output"]["message"]["content"][0]["text"]
        span.set_attribute(
            "gen_ai.output.messages",
            json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": text}],
                        **({"finish_reason": stop_reason} if stop_reason else {}),
                    }
                ]
            ),
        )

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.input.messages": json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"][0]["text"]}]} for m in messages]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": text}],
                        "finish_reason": stop_reason,
                    }
                ]
            ),
        }
        if stop_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [stop_reason]
        if usage.get("inputTokens") is not None:
            event_attrs["gen_ai.usage.input_tokens"] = usage["inputTokens"]
        if usage.get("outputTokens") is not None:
            event_attrs["gen_ai.usage.output_tokens"] = usage["outputTokens"]
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {text[:60]}")


def run_converse_tool_call_reference(client):
    """Scenario: Bedrock Converse API with tool calling reference implementation."""
    print("  [chat_tool_call] Bedrock Converse API with tool calling (reference implementation)")
    request_model = "anthropic.claude-3-haiku-20240307-v1:0"
    tool_spec = {
        "toolSpec": {
            "name": "get_weather",
            "description": "Get the current weather",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                }
            },
        }
    }
    tool_config = {"tools": [tool_spec]}
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "chat anthropic.claude-3-haiku-20240307-v1:0", attributes=span_attributes_2
    ) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_config["tools"]))
        messages = [
            {
                "role": "user",
                "content": [{"text": "What's the weather in Seattle?"}],
            }
        ]
        response = client.converse(
            modelId=request_model,
            messages=messages,
            toolConfig=tool_config,
        )
        stop_reason = response.get("stopReason")
        if stop_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [stop_reason])
        usage = response.get("usage", {})
        if usage.get("inputTokens") is not None:
            span.set_attribute("gen_ai.usage.input_tokens", usage["inputTokens"])
        if usage.get("outputTokens") is not None:
            span.set_attribute("gen_ai.usage.output_tokens", usage["outputTokens"])
        content = response["output"]["message"]["content"]
        if content and "toolUse" in content[0]:
            tool_use = content[0]["toolUse"]
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
            }
            with _reference_tracer.start_as_current_span(
                "execute_tool get_weather", attributes=tool_span_attributes
            ) as tool_span:
                tool_span.set_attribute("gen_ai.tool.name", tool_use["name"])
                tool_span.set_attribute("gen_ai.tool.description", tool_spec["toolSpec"]["description"])
                tool_span.set_attribute("gen_ai.tool.type", "function")
                tool_span.set_attribute("gen_ai.tool.call.id", tool_use["toolUseId"])
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(tool_use.get("input", {})))
                result = f"Sunny in {tool_use.get('input', {}).get('location', 'unknown')}"
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            print(f"    -> tool_call: {tool_use['name']}")
        else:
            print(f"    -> {content[0]['text'][:60]}")


def run_embeddings_reference(client):
    """Scenario: Bedrock Titan Embeddings with reference implementation."""
    import json as _json

    print("  [embeddings] Bedrock Titan Embeddings (reference implementation)")
    request_model = "amazon.titan-embed-text-v2:0"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_3 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_3["server.address"] = host
    if port is not None:
        span_attributes_3["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "embeddings amazon.titan-embed-text-v2:0", attributes=span_attributes_3
    ) as span:
        response = client.invoke_model(
            modelId=request_model,
            contentType="application/json",
            accept="application/json",
            body=_json.dumps({"inputText": "Hello, world!"}),
        )
        result = _json.loads(response["body"].read())
        if result.get("inputTextTokenCount") is not None:
            span.set_attribute("gen_ai.usage.input_tokens", result["inputTextTokenCount"])
        print(f"    -> embedding dim: {len(result['embedding'])}")


def main():
    print("=== Reference Implementation: AWS Bedrock ===")

    tp, lp, mp = setup_otel()

    client = create_bedrock_client()

    run_converse_reference(client)
    run_converse_tool_call_reference(client)
    run_embeddings_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
