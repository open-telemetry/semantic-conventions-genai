"""Reference implementation for Ollama.

Exercises: chat and embeddings
against a mock Ollama server, with manual OTel spans and metrics.
"""

import os
from time import perf_counter

from opentelemetry.trace import SpanKind
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
_reference_meter = reference_meter()

_inference_duration = _reference_meter.create_histogram(
    "gen_ai.client.inference.duration",
    unit="s",
    description="GenAI client inference operation duration.",
)
_operation_input_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used per inference operation.",
)
_operation_output_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used per inference operation.",
)
_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used, including cached tokens.",
)
_output_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used, including reasoning tokens.",
)
_embeddings_duration = _reference_meter.create_histogram(
    "gen_ai.client.embeddings.duration",
    unit="s",
    description="GenAI client embeddings operation duration.",
)
_embeddings_input_tokens = _reference_meter.create_histogram(
    "gen_ai.client.embeddings.operation.input_tokens",
    unit="{token}",
    description="The number of input tokens used per embeddings operation.",
)


def _metric_attributes(operation, request_model, response_model, host, port):
    """Build the attributes shared by the Ollama instruments for one operation."""
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
    }
    if response_model:
        attributes["gen_ai.response.model"] = response_model
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _record_inference_usage(input_tokens, output_tokens, metric_attributes):
    """Record the usage instruments from the same gen_ai.usage.* values the span carries.

    The per-operation histograms are recorded for every inference operation: the
    value is the token count returned by the provider, or 0 when the response
    contains no token usage. Ollama reports no per-modality token breakdown, so
    every counter point goes to the unknown modality, and the usage counters are
    only incremented for known positive counts.
    """
    modality_attributes = {**metric_attributes, "gen_ai.token.modality": "unknown"}
    _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
    _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
    if input_tokens:
        _input_tokens.add(input_tokens, modality_attributes)
    if output_tokens:
        _output_tokens.add(output_tokens, modality_attributes)


def run_chat(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "llama3.2"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    # One options object handed to the SDK call; the ollama.request.* and
    # gen_ai.request.* span attributes read their values from it.
    request_options = {
        "num_predict": 100,
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
        "stop": ["\n\n"],
        "seed": 42,
        "num_ctx": 2048,
        "num_batch": 512,
        "num_gpu": 1,
        "main_gpu": 0,
        "low_vram": True,
        "f16_kv": True,
    }
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "gen_ai.request.max_tokens": request_options["num_predict"],
        "gen_ai.request.temperature": request_options["temperature"],
        "gen_ai.request.top_p": request_options["top_p"],
        "gen_ai.request.top_k": request_options["top_k"],
        "gen_ai.request.stop_sequences": request_options["stop"],
        "gen_ai.request.seed": request_options["seed"],
        "ollama.request.base_url": MOCK_BASE_URL,
        "ollama.request.num_ctx": request_options["num_ctx"],
        "ollama.request.num_batch": request_options["num_batch"],
        "ollama.request.num_gpu": request_options["num_gpu"],
        "ollama.request.main_gpu": request_options["main_gpu"],
        "ollama.request.low_vram": request_options["low_vram"],
        "ollama.request.f16_kv": request_options["f16_kv"],
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    input_tokens = None
    output_tokens = None
    response_model = None
    with _reference_tracer.start_as_current_span(
        "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        resp = client.chat(
            model=request_model,
            messages=messages,
            stream=False,
            options=request_options,
        )
        elapsed = perf_counter() - started_at
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
            response_model = resp.model
        if resp.done_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason])
        if resp.prompt_eval_count is not None:
            input_tokens = int(resp.prompt_eval_count)
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if resp.eval_count is not None:
            output_tokens = int(resp.eval_count)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if resp.total_duration is not None:
            span.set_attribute("ollama.response.total_duration", int(resp.total_duration))
        if resp.load_duration is not None:
            span.set_attribute("ollama.response.load_duration", int(resp.load_duration))

        metric_attributes = _metric_attributes("chat", request_model, response_model, host, port)
        _inference_duration.record(elapsed, metric_attributes)
        _record_inference_usage(input_tokens, output_tokens, metric_attributes)

        content = resp.message.content
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": request_model,
            "gen_ai.request.max_tokens": request_options["num_predict"],
            "gen_ai.request.temperature": request_options["temperature"],
            "gen_ai.request.top_p": request_options["top_p"],
            "gen_ai.request.top_k": request_options["top_k"],
            "gen_ai.request.stop_sequences": request_options["stop"],
            "gen_ai.request.seed": request_options["seed"],
            "gen_ai.input.messages": [
                {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
            ],
            "gen_ai.output.messages": [
                {
                    "role": "assistant",
                    "parts": [{"type": "text", "content": content}],
                }
            ],
        }
        if resp.model:
            event_attrs["gen_ai.response.model"] = resp.model
        if resp.done_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason]
        if input_tokens is not None:
            event_attrs["gen_ai.usage.input_tokens"] = input_tokens
        if output_tokens is not None:
            event_attrs["gen_ai.usage.output_tokens"] = output_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {content[:60]}")


def run_embed(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "nomic-embed-text"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "ollama.request.base_url": MOCK_BASE_URL,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    input_text = "Hello, world!"
    input_token_count = 0
    with _reference_tracer.start_as_current_span(
        "embeddings nomic-embed-text", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        resp = client.embed(model=request_model, input=input_text)
        elapsed = perf_counter() - started_at
        metric_attributes = _metric_attributes("embeddings", request_model, resp.model, host, port)
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.embeddings:
            span.set_attribute("gen_ai.embeddings.dimension.count", len(resp.embeddings[0]))
        if resp.prompt_eval_count is not None:
            input_token_count = int(resp.prompt_eval_count)
            span.set_attribute("gen_ai.usage.input_tokens", input_token_count)
        if resp.total_duration is not None:
            span.set_attribute("ollama.response.total_duration", int(resp.total_duration))
        if resp.load_duration is not None:
            span.set_attribute("ollama.response.load_duration", int(resp.load_duration))
        _embeddings_duration.record(elapsed, metric_attributes)
        _embeddings_input_tokens.record(input_token_count, metric_attributes)
        dimension = len(resp.embeddings[0]) if resp.embeddings else 0
        print(f"    -> embedding dim: {dimension}")


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    import ollama

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client)
    run_embed(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
