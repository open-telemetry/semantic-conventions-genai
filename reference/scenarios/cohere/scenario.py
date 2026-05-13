"""Reference implementation for Cohere.

Exercises: chat, embeddings
against a mock Cohere server, with manual OTel spans.
"""

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


def run_chat(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "command-r-plus"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "cohere",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat command-r-plus", attributes=span_attributes) as span:
        messages = [{"role": "user", "content": "Say hello."}]
        resp = client.chat(
            model=request_model,
            messages=messages,
        )
        if hasattr(resp, "id") and resp.id:
            span.set_attribute("gen_ai.response.id", resp.id)
        if hasattr(resp, "finish_reason") and resp.finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [resp.finish_reason])
        if hasattr(resp, "usage") and resp.usage and hasattr(resp.usage, "tokens") and resp.usage.tokens:
            if hasattr(resp.usage.tokens, "input_tokens"):
                span.set_attribute("gen_ai.usage.input_tokens", int(resp.usage.tokens.input_tokens))
            if hasattr(resp.usage.tokens, "output_tokens"):
                span.set_attribute("gen_ai.usage.output_tokens", int(resp.usage.tokens.output_tokens))

        # Emit inference operation details event
        content = resp.message.content[0].text
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.input.messages": json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": content}],
                        "finish_reason": resp.finish_reason if hasattr(resp, "finish_reason") else None,
                    }
                ]
            ),
        }
        if hasattr(resp, "id") and resp.id:
            event_attrs["gen_ai.response.id"] = resp.id
        if hasattr(resp, "finish_reason") and resp.finish_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [resp.finish_reason]
        if hasattr(resp, "usage") and resp.usage and hasattr(resp.usage, "tokens") and resp.usage.tokens:
            if hasattr(resp.usage.tokens, "input_tokens"):
                event_attrs["gen_ai.usage.input_tokens"] = int(resp.usage.tokens.input_tokens)
            if hasattr(resp.usage.tokens, "output_tokens"):
                event_attrs["gen_ai.usage.output_tokens"] = int(resp.usage.tokens.output_tokens)
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {content[:60]}")


def run_chat_tool_call(client):
    """Scenario: chat with tool calling with reference implementation."""
    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "command-r-plus"
    request_tool = {
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
    tools = [request_tool]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "cohere",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span("chat command-r-plus", attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        resp = client.chat(
            model=request_model,
            messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
            tools=tools,
        )
        if hasattr(resp, "id") and resp.id:
            span.set_attribute("gen_ai.response.id", resp.id)
        if hasattr(resp, "finish_reason") and resp.finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [resp.finish_reason])
        if hasattr(resp, "usage") and resp.usage and hasattr(resp.usage, "tokens") and resp.usage.tokens:
            if hasattr(resp.usage.tokens, "input_tokens"):
                span.set_attribute("gen_ai.usage.input_tokens", int(resp.usage.tokens.input_tokens))
            if hasattr(resp.usage.tokens, "output_tokens"):
                span.set_attribute("gen_ai.usage.output_tokens", int(resp.usage.tokens.output_tokens))
        content = resp.message.content[0].text
        if hasattr(resp.message, "tool_calls") and resp.message.tool_calls:
            tool_call = resp.message.tool_calls[0]
            arguments_json = tool_call.function.arguments or "{}"
            arguments = json.loads(arguments_json)
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
            }
            with _reference_tracer.start_as_current_span(
                "execute_tool get_weather", attributes=tool_span_attributes
            ) as tool_span:
                tool_span.set_attribute("gen_ai.tool.name", tool_call.function.name)
                tool_span.set_attribute("gen_ai.tool.description", request_tool["function"]["description"])
                tool_span.set_attribute("gen_ai.tool.type", request_tool["type"])
                tool_span.set_attribute("gen_ai.tool.call.id", tool_call.id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
                result = f"Sunny in {arguments.get('location', 'unknown')}"
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            print(f"    -> tool_call: {tool_call.function.name}")
        else:
            print(f"    -> {content[:60]}")


def run_embeddings(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "embed-v4.0"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_3 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "cohere",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_3["server.address"] = host
    if port is not None:
        span_attributes_3["server.port"] = port
    with _reference_tracer.start_as_current_span("embeddings embed-v4.0", attributes=span_attributes_3) as span:
        resp = client.embed(
            model=request_model,
            texts=["Hello, world!"],
            input_type="search_document",
            embedding_types=["float"],
        )
        if hasattr(resp, "meta") and resp.meta and hasattr(resp.meta, "billed_units") and resp.meta.billed_units:
            input_tokens = getattr(resp.meta.billed_units, "input_tokens", None)
            if input_tokens is not None:
                span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens))
        print(f"    -> embedding dim: {len(resp.embeddings.float_[0])}")


def main():
    print("=== Reference Implementation: Cohere ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    import cohere

    client = cohere.ClientV2(
        api_key="mock-key",
        base_url=MOCK_BASE_URL,
    )

    run_chat(client)
    run_chat_tool_call(client)
    run_embeddings(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
