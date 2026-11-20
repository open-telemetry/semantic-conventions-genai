"""Reference implementation for Groq."""

import argparse
import json
import os
import time

from opentelemetry.trace import SpanKind, StatusCode
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
_TOKEN_BUCKETS = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]
_input_tokens = _meter.create_histogram(
    "gen_ai.client.inference.operation.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=_TOKEN_BUCKETS,
)
_output_tokens = _meter.create_histogram(
    "gen_ai.client.inference.operation.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=_TOKEN_BUCKETS,
)
_input_token_usage = _meter.create_counter(
    "gen_ai.client.inference.usage.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used, including cached tokens.",
)
_output_token_usage = _meter.create_counter(
    "gen_ai.client.inference.usage.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used, including reasoning tokens.",
)
_cache_read_input_token_usage = _meter.create_counter(
    "gen_ai.client.inference.usage.cache_read.input_tokens",
    unit="{token}",
    description="The number of input tokens served from a provider-managed cache.",
)
_reasoning_output_token_usage = _meter.create_counter(
    "gen_ai.client.inference.usage.reasoning.output_tokens",
    unit="{token}",
    description="The number of output tokens used for reasoning (e.g. chain-of-thought, extended thinking).",
)
_inference_duration = _meter.create_histogram(
    "gen_ai.client.inference.duration",
    unit="s",
    description="GenAI client inference operation duration.",
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


def _usage_details(usage):
    """Return the cached input and reasoning output counts Groq reported, or 0."""
    prompt_details = usage.prompt_tokens_details if usage else None
    completion_details = usage.completion_tokens_details if usage else None
    return (
        prompt_details.cached_tokens if prompt_details else 0,
        completion_details.reasoning_tokens if completion_details else 0,
    )


def _set_usage_details(span, cache_read_tokens, reasoning_tokens):
    if cache_read_tokens > 0:
        span.set_attribute("gen_ai.usage.cache_read.input_tokens", cache_read_tokens)
    if reasoning_tokens > 0:
        span.set_attribute("gen_ai.usage.reasoning.output_tokens", reasoning_tokens)


def _add_usage_details(cache_read_tokens, reasoning_tokens, modality_attributes):
    if cache_read_tokens > 0:
        _cache_read_input_token_usage.add(cache_read_tokens, modality_attributes)
    if reasoning_tokens > 0:
        reasoning_attributes = {k: v for k, v in modality_attributes.items() if k != "gen_ai.token.modality"}
        _reasoning_output_token_usage.add(reasoning_tokens, reasoning_attributes)


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "llama-3.1-8b-instant"
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "groq",
        "gen_ai.request.model": request_model,
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat llama-3.1-8b-instant", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        messages = [{"role": "user", "content": "Say hello."}]
        metric_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": request_model,
            "server.address": _SERVER_ADDRESS,
            "server.port": _SERVER_PORT,
        }
        input_tokens = output_tokens = cache_read_tokens = reasoning_tokens = 0
        start_time = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=request_model,
                messages=messages,
            )
            metric_attributes["gen_ai.response.model"] = resp.model
            span.set_attribute("gen_ai.response.model", resp.model)
            span.set_attribute("gen_ai.response.id", resp.id)
            span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
            if resp.usage:
                span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
                input_tokens = resp.usage.prompt_tokens or 0
                output_tokens = resp.usage.completion_tokens or 0
                cache_read_tokens, reasoning_tokens = _usage_details(resp.usage)
                _set_usage_details(span, cache_read_tokens, reasoning_tokens)
        except Exception as exc:
            metric_attributes["error.type"] = type(exc).__name__
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(StatusCode.ERROR)
            raise
        finally:
            _inference_duration.record(time.perf_counter() - start_time, metric_attributes)
            _input_tokens.record(input_tokens, metric_attributes)
            _output_tokens.record(output_tokens, metric_attributes)
            modality_attributes = {**metric_attributes, "gen_ai.token.modality": "unknown"}
            if input_tokens > 0:
                _input_token_usage.add(input_tokens, modality_attributes)
            if output_tokens > 0:
                _output_token_usage.add(output_tokens, modality_attributes)
            _add_usage_details(cache_read_tokens, reasoning_tokens, modality_attributes)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [c.finish_reason for c in resp.choices],
            "gen_ai.input.messages": [
                {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
            ],
            "gen_ai.output.messages": [
                {
                    "role": c.message.role,
                    "parts": [{"type": "text", "content": c.message.content}],
                }
                for c in resp.choices
            ],
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
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat llama-3.1-8b-instant", kind=SpanKind.CLIENT, attributes=span_attributes_2
    ) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in request_messages],
        )
        metric_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": request_model,
            "server.address": _SERVER_ADDRESS,
            "server.port": _SERVER_PORT,
        }
        input_tokens = output_tokens = cache_read_tokens = reasoning_tokens = 0
        start_time = time.perf_counter()
        try:
            stream = client.chat.completions.create(
                model=request_model,
                messages=request_messages,
                stream=True,
            )
            text = ""
            model = None
            response_id = None
            finish_reasons = []
            usage = None
            with stream:
                for chunk in stream:
                    model = model or getattr(chunk, "model", None)
                    response_id = response_id or getattr(chunk, "id", None)
                    usage = chunk.usage or (chunk.x_groq and chunk.x_groq.usage) or usage
                    if model:
                        metric_attributes["gen_ai.response.model"] = model
                    if usage:
                        input_tokens = usage.prompt_tokens or 0
                        output_tokens = usage.completion_tokens or 0
                        cache_read_tokens, reasoning_tokens = _usage_details(usage)
                    if chunk.choices and chunk.choices[0].delta.content:
                        text += chunk.choices[0].delta.content
                    if chunk.choices and chunk.choices[0].finish_reason:
                        finish_reasons.append(chunk.choices[0].finish_reason)
                    if chunk.x_groq and chunk.x_groq.error is not None:
                        # The SDK yields the provider error as data and may finish normally.
                        error_type = "groq.stream_error"
                        metric_attributes["error.type"] = error_type
                        span.set_attribute("error.type", error_type)
                        span.set_status(StatusCode.ERROR)
                        if not finish_reasons:
                            finish_reasons.append("error")
                        break
            if model:
                span.set_attribute("gen_ai.response.model", model)
            if response_id:
                span.set_attribute("gen_ai.response.id", response_id)
            if finish_reasons:
                span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
            if usage:
                span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
                _set_usage_details(span, cache_read_tokens, reasoning_tokens)
        except Exception as exc:
            metric_attributes["error.type"] = type(exc).__name__
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(StatusCode.ERROR)
            raise
        finally:
            _inference_duration.record(time.perf_counter() - start_time, metric_attributes)
            _input_tokens.record(input_tokens, metric_attributes)
            _output_tokens.record(output_tokens, metric_attributes)
            modality_attributes = {**metric_attributes, "gen_ai.token.modality": "unknown"}
            modality_attributes.pop("error.type", None)
            if input_tokens > 0:
                _input_token_usage.add(input_tokens, modality_attributes)
            if output_tokens > 0:
                _output_token_usage.add(output_tokens, modality_attributes)
            _add_usage_details(cache_read_tokens, reasoning_tokens, modality_attributes)
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
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat llama-3.1-8b-instant", kind=SpanKind.CLIENT, attributes=span_attributes_3
    ) as span:
        span.set_attribute("gen_ai.tool.definitions", [{"type": t["type"], **t["function"]} for t in tools])
        metric_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": request_model,
            "server.address": _SERVER_ADDRESS,
            "server.port": _SERVER_PORT,
        }
        input_tokens = output_tokens = cache_read_tokens = reasoning_tokens = 0
        start_time = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=request_model,
                messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
                tools=tools,
            )
            metric_attributes["gen_ai.response.model"] = resp.model
            span.set_attribute("gen_ai.response.model", resp.model)
            span.set_attribute("gen_ai.response.id", resp.id)
            span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
            if resp.usage:
                span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
                input_tokens = resp.usage.prompt_tokens or 0
                output_tokens = resp.usage.completion_tokens or 0
                cache_read_tokens, reasoning_tokens = _usage_details(resp.usage)
                _set_usage_details(span, cache_read_tokens, reasoning_tokens)
        except Exception as exc:
            metric_attributes["error.type"] = type(exc).__name__
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(StatusCode.ERROR)
            raise
        finally:
            _inference_duration.record(time.perf_counter() - start_time, metric_attributes)
            _input_tokens.record(input_tokens, metric_attributes)
            _output_tokens.record(output_tokens, metric_attributes)
            modality_attributes = {**metric_attributes, "gen_ai.token.modality": "unknown"}
            if input_tokens > 0:
                _input_token_usage.add(input_tokens, modality_attributes)
            if output_tokens > 0:
                _output_token_usage.add(output_tokens, modality_attributes)
            _add_usage_details(cache_read_tokens, reasoning_tokens, modality_attributes)
        choice = resp.choices[0]
        if choice.message.tool_calls:
            # The client returns the tool call; running it is app code the client
            # never sees, so there is no execute_tool span to emit here.
            print(f"    -> tool_call: {choice.message.tool_calls[0].function.name}")
        else:
            print(f"    -> {choice.message.content[:60]}")


def _stream_fixture_response(request, *, early_stop):
    """Serve Groq-shaped SSE through the regular SDK parser."""
    import httpx

    assert request.url.path.endswith("/chat/completions")
    assert json.loads(request.content)["stream"] is True
    chunk = {
        "id": "groq-stream",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "llama-3.1-8b-instant",
    }
    first = {
        **chunk,
        "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}],
    }
    last = {
        **chunk,
        "choices": [],
        "x_groq": {
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "total_tokens": 7,
                "prompt_tokens_details": {"cached_tokens": 3},
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        },
    }
    if early_stop:
        last["x_groq"]["error"] = "stream stopped by Groq"
    else:
        last["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in (first, last))
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body + "data: [DONE]\n\n")


def main(*, stream_fixture=None):
    print("=== Reference Implementation: Groq ===")

    import groq

    tp, lp, mp = setup_otel()
    try:
        if stream_fixture is not None:
            from functools import partial

            import httpx

            respond = partial(_stream_fixture_response, early_stop=stream_fixture == "early-stop")
            with groq.Groq(
                base_url=MOCK_BASE_URL,
                api_key="mock-key",
                http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            ) as client:
                run_chat_streaming_reference(client)
            return

        with groq.Groq(base_url=MOCK_BASE_URL, api_key="mock-key") as client:
            run_chat_reference(client)
            run_chat_streaming_reference(client)
            run_chat_tool_call_reference(client)
    finally:
        flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream-fixture", choices=["usage", "early-stop"])
    main(stream_fixture=parser.parse_args().stream_fixture)
