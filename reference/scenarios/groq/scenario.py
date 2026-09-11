"""Reference implementation for Groq."""

import json
import os
import time

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()
_meter = reference_meter()
# Bucket boundaries advised for each metric by docs/gen-ai/gen-ai-metrics.md.
_token_usage = _meter.create_histogram(
    "gen_ai.client.token.usage",
    unit="{token}",
    description="Number of input and output tokens used.",
    explicit_bucket_boundaries_advisory=[
        1,
        4,
        16,
        64,
        256,
        1024,
        4096,
        16384,
        65536,
        262144,
        1048576,
        4194304,
        16777216,
        67108864,
    ],
)
_operation_duration = _meter.create_histogram(
    "gen_ai.client.operation.duration",
    unit="s",
    description="GenAI operation duration.",
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
_SERVER_ADDRESS, _SERVER_PORT = mock_server_host_port(MOCK_BASE_URL)


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "llama-3.1-8b-instant"
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "groq",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat llama-3.1-8b-instant", attributes=span_attributes) as span:
        messages = [{"role": "user", "content": "Say hello."}]
        start_time = time.perf_counter()
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
        )
        duration = time.perf_counter() - start_time
        _operation_duration.record(
            duration,
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "groq",
                "gen_ai.request.model": request_model,
                "gen_ai.response.model": resp.model,
                "server.address": _SERVER_ADDRESS,
                "server.port": _SERVER_PORT,
            },
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            _token_usage.record(
                resp.usage.prompt_tokens,
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "groq",
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "gen_ai.token.type": "input",
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                },
            )
            _token_usage.record(
                resp.usage.completion_tokens,
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "groq",
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "gen_ai.token.type": "output",
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                },
            )

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [c.finish_reason for c in resp.choices],
            "gen_ai.input.messages": json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": c.message.role,
                        "parts": [{"type": "text", "content": c.message.content}],
                    }
                    for c in resp.choices
                ]
            ),
        }
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.prompt_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.completion_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_chat_streaming_reference(client):
    """Scenario: streaming chat completion with reference implementation."""
    print("  [chat_streaming] streaming chat completion (reference implementation)")
    request_model = "llama-3.1-8b-instant"
    request_messages = [{"role": "user", "content": "Tell me a joke."}]
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "groq",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat llama-3.1-8b-instant", attributes=span_attributes_2) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in request_messages]
            ),
        )
        start_time = time.perf_counter()
        stream = client.chat.completions.create(
            model=request_model,
            messages=request_messages,
            stream=True,
        )
        text = ""
        model = None
        response_id = None
        finish_reasons = []
        for chunk in stream:
            model = model or getattr(chunk, "model", None)
            response_id = response_id or getattr(chunk, "id", None)
            if chunk.choices and chunk.choices[0].delta.content:
                text += chunk.choices[0].delta.content
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reasons.append(chunk.choices[0].finish_reason)
        if model:
            span.set_attribute("gen_ai.response.model", model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        # The stream carries no usage block, so token.usage MUST NOT be reported here.
        _operation_duration.record(
            time.perf_counter() - start_time,
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "groq",
                "gen_ai.request.model": request_model,
                "gen_ai.response.model": model,
                "server.address": _SERVER_ADDRESS,
                "server.port": _SERVER_PORT,
            },
        )
        print(f"    -> {text[:60]}")


def run_chat_tool_call_reference(client):
    """Scenario: chat with tool calling with reference implementation."""
    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "llama-3.1-8b-instant"
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
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "groq",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat llama-3.1-8b-instant", attributes=span_attributes_3) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        start_time = time.perf_counter()
        resp = client.chat.completions.create(
            model=request_model,
            messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
            tools=tools,
        )
        duration = time.perf_counter() - start_time
        _operation_duration.record(
            duration,
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "groq",
                "gen_ai.request.model": request_model,
                "gen_ai.response.model": resp.model,
                "server.address": _SERVER_ADDRESS,
                "server.port": _SERVER_PORT,
            },
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            _token_usage.record(
                resp.usage.prompt_tokens,
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "groq",
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "gen_ai.token.type": "input",
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                },
            )
            _token_usage.record(
                resp.usage.completion_tokens,
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "groq",
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "gen_ai.token.type": "output",
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                },
            )
        choice = resp.choices[0]
        if choice.message.tool_calls:
            # The client returns the tool call; running it is app code the client
            # never sees, so there is no execute_tool span to emit here.
            print(f"    -> tool_call: {choice.message.tool_calls[0].function.name}")
        else:
            print(f"    -> {choice.message.content[:60]}")


def main():
    print("=== Reference Implementation: Groq ===")

    tp, lp, mp = setup_otel()

    import groq

    client = groq.Groq(base_url=MOCK_BASE_URL, api_key="mock-key")

    run_chat_reference(client)
    run_chat_streaming_reference(client)
    run_chat_tool_call_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
