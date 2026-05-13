"""Reference implementation for OpenAI."""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "gpt-4o-mini"
    request_choice_count = 2
    request_max_tokens = 32
    request_temperature = 0.2
    request_seed = 7
    request_stop_sequences = ["###", "<END>"]
    request_frequency_penalty = 0.1
    request_presence_penalty = 0.2
    request_top_p = 0.9
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    system_instructions = [
        {"parts": [{"type": "text", "content": message["content"]}]}
        for message in messages
        if message["role"] in {"system", "developer"}
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    input_messages = json.dumps(
        [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
    )
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.request.choice.count", request_choice_count)
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute("gen_ai.request.seed", request_seed)
        span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
        span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
        span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
        span.set_attribute("gen_ai.request.top_p", request_top_p)
        span.set_attribute("gen_ai.input.messages", input_messages)
        if system_instructions:
            span.set_attribute("gen_ai.system_instructions", json.dumps(system_instructions))
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
            n=request_choice_count,
            max_tokens=request_max_tokens,
            temperature=request_temperature,
            seed=request_seed,
            stop=request_stop_sequences,
            frequency_penalty=request_frequency_penalty,
            presence_penalty=request_presence_penalty,
            top_p=request_top_p,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        output_messages = [
            {
                "role": c.message.role,
                "parts": [{"type": "text", "content": c.message.content}],
                "finish_reason": c.finish_reason,
            }
            for c in resp.choices
        ]
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            cached_tokens = getattr(
                getattr(resp.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            if cached_tokens is not None:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", cached_tokens)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [c.finish_reason for c in resp.choices],
            "gen_ai.input.messages": input_messages,
            "gen_ai.output.messages": json.dumps(output_messages),
        }
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.prompt_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.completion_tokens
            cached_tokens = getattr(
                getattr(resp.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            if cached_tokens is not None:
                event_attrs["gen_ai.usage.cache_read.input_tokens"] = cached_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_chat_streaming_reference(client):
    """Scenario: streaming chat completion with reference implementation."""
    print("  [chat_streaming] streaming chat completion (reference implementation)")
    request_model = "gpt-4o-mini"
    request_messages = [{"role": "user", "content": "Tell me a joke."}]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in request_messages]
            ),
        )
        stream = client.chat.completions.create(
            model=request_model,
            messages=request_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        text = ""
        model = None
        response_id = None
        finish_reasons = []
        input_tokens = None
        output_tokens = None
        for chunk in stream:
            model = model or getattr(chunk, "model", None)
            response_id = response_id or getattr(chunk, "id", None)
            if chunk.choices and chunk.choices[0].delta.content:
                text += chunk.choices[0].delta.content
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reasons.append(chunk.choices[0].finish_reason)
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
        if model:
            span.set_attribute("gen_ai.response.model", model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        if text:
            output_message = {
                "role": "assistant",
                "parts": [{"type": "text", "content": text}],
            }
            if finish_reasons:
                output_message["finish_reason"] = finish_reasons[-1]
            span.set_attribute("gen_ai.output.messages", json.dumps([output_message]))
        if input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        print(f"    -> {text[:60]}")


def run_chat_tool_call_reference(client):
    """Scenario: chat with tool calling with reference implementation."""
    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "gpt-4o-mini"

    def get_weather(location: str) -> str:
        return f"Sunny in {location}"

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
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_3["server.address"] = host
    if port is not None:
        span_attributes_3["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_3) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        resp = client.chat.completions.create(
            model=request_model,
            messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
            tools=tools,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
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
                result = get_weather(arguments["location"])
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            print(f"    -> tool_call: {tool_call.function.name}")
        else:
            print(f"    -> {choice.message.content[:60]}")


def run_embeddings_reference(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "text-embedding-3-small"
    request_encoding_format = "base64"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_4["server.address"] = host
    if port is not None:
        span_attributes_4["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "embeddings text-embedding-3-small", attributes=span_attributes_4
    ) as span:
        span.set_attribute("gen_ai.request.encoding_formats", [request_encoding_format])
        resp = client.embeddings.create(
            model=request_model,
            input="Hello, world!",
            encoding_format=request_encoding_format,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        if resp.data and resp.data[0].embedding is not None:
            span.set_attribute("gen_ai.embeddings.dimension.count", len(resp.data[0].embedding))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
        print(f"    -> embedding dim: {len(resp.data[0].embedding)}")


def main():
    print("=== Reference Implementation: OpenAI Reference Implementation ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")

    run_chat_reference(client)
    run_chat_streaming_reference(client)
    run_chat_tool_call_reference(client)
    run_embeddings_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
