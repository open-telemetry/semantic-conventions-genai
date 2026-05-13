"""Reference implementation for Mistral AI.

Exercises: chat, chat_streaming, embeddings
against a mock server, with manual OTel spans.
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


def _disable_sdk_tracing(client) -> None:
    hooks = client.sdk_configuration._hooks

    from mistralai.client._hooks.tracing import TracingHook

    hooks.before_request_hooks = [hook for hook in hooks.before_request_hooks if not isinstance(hook, TracingHook)]
    hooks.after_success_hooks = [hook for hook in hooks.after_success_hooks if not isinstance(hook, TracingHook)]
    hooks.after_error_hooks = [hook for hook in hooks.after_error_hooks if not isinstance(hook, TracingHook)]


def run_chat(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "mistral-large-latest"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    messages = [{"role": "user", "content": "Say hello."}]
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "mistral_ai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat mistral-large-latest", attributes=span_attributes) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]),
        )
        resp = client.chat.complete(
            model=request_model,
            messages=messages,
        )
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.id:
            span.set_attribute("gen_ai.response.id", resp.id)
        if resp.choices:
            span.set_attribute(
                "gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices if c.finish_reason]
            )
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)

        # Emit inference operation details event
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
                        "parts": [{"type": "text", "content": c.message.content}],
                        "finish_reason": c.finish_reason,
                    }
                    for c in resp.choices
                ]
            ),
        }
        if resp.model:
            event_attrs["gen_ai.response.model"] = resp.model
        if resp.id:
            event_attrs["gen_ai.response.id"] = resp.id
        if resp.choices:
            event_attrs["gen_ai.response.finish_reasons"] = [c.finish_reason for c in resp.choices if c.finish_reason]
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.prompt_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.completion_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_chat_tool_call(client):
    """Scenario: chat with tool calling with reference implementation."""
    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "mistral-large-latest"
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
    messages = [{"role": "user", "content": "What's the weather in Seattle?"}]
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "mistral_ai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span("chat mistral-large-latest", attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]),
        )
        resp = client.chat.complete(
            model=request_model,
            messages=messages,
            tools=tools,
        )
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.id:
            span.set_attribute("gen_ai.response.id", resp.id)
        if resp.choices:
            span.set_attribute(
                "gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices if c.finish_reason]
            )
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        choice = resp.choices[0]
        if choice.message.tool_calls:
            tool_call = choice.message.tool_calls[0]
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
            print(f"    -> {choice.message.content[:60]}")


def run_chat_streaming(client):
    """Scenario: streaming chat completion with reference implementation."""
    print("  [chat_streaming] streaming chat completion (reference implementation)")
    request_model = "mistral-large-latest"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    messages = [{"role": "user", "content": "Tell me a joke."}]
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "mistral_ai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_3["server.address"] = host
    if port is not None:
        span_attributes_3["server.port"] = port
    with _reference_tracer.start_as_current_span("chat mistral-large-latest", attributes=span_attributes_3) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]),
        )
        text = ""
        response_model = None
        response_id = None
        finish_reasons = []
        input_tokens = None
        output_tokens = None
        stream = client.chat.stream(
            model=request_model,
            messages=messages,
        )
        for event in stream:
            data = getattr(event, "data", None)
            if data is None:
                continue
            response_model = response_model or getattr(data, "model", None)
            response_id = response_id or getattr(data, "id", None)
            usage = getattr(data, "usage", None)
            if usage is not None:
                input_tokens = getattr(usage, "prompt_tokens", input_tokens)
                output_tokens = getattr(usage, "completion_tokens", output_tokens)
            if data.choices and data.choices[0].delta.content:
                text += data.choices[0].delta.content
            if data.choices and data.choices[0].finish_reason:
                finish_reasons.append(data.choices[0].finish_reason)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        if input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if text:
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": text}],
                            **({"finish_reason": finish_reasons[-1]} if finish_reasons else {}),
                        }
                    ]
                ),
            )
        print(f"    -> {text[:60]}")


def run_embeddings(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "mistral-embed"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "mistral_ai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_4["server.address"] = host
    if port is not None:
        span_attributes_4["server.port"] = port
    with _reference_tracer.start_as_current_span("embeddings mistral-embed", attributes=span_attributes_4) as span:
        resp = client.embeddings.create(
            model=request_model,
            inputs=["Hello, world!"],
        )
        if getattr(resp, "model", None):
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
        print(f"    -> embedding dim: {len(resp.data[0].embedding)}")


def main():
    print("=== Reference Implementation: Mistral AI ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    from mistralai.client import Mistral

    client = Mistral(
        api_key="mock-key",
        server_url=MOCK_BASE_URL,
    )
    _disable_sdk_tracing(client)

    run_chat(client)
    run_chat_tool_call(client)
    run_chat_streaming(client)

    run_embeddings(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
