"""Reference implementation for Ollama.

Exercises: chat and embeddings
against a mock Ollama server, with manual OTel spans and metrics.
"""

import os
import traceback
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
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

# A host that accepts no connections, used to exercise the SDK failure paths.
UNREACHABLE_BASE_URL = "http://127.0.0.1:1"

# Explicit bucket boundaries recommended by docs/gen-ai/client-inference.md,
# docs/gen-ai/client-embeddings.md, and docs/gen-ai/gen-ai-token-metrics.md
# for the duration and per-operation token histograms.
_DURATION_BOUNDARIES = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]
_TOKEN_BOUNDARIES = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]

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


def _bucket_view(instrument_name, boundaries):
    """Return a metric view pinning the recommended explicit bucket boundaries."""
    return View(instrument_name=instrument_name, aggregation=ExplicitBucketHistogramAggregation(boundaries=boundaries))


def _metric_views():
    """Explicit bucket boundaries for the duration and token histograms."""
    return (
        _bucket_view("gen_ai.client.inference.duration", _DURATION_BOUNDARIES),
        _bucket_view("gen_ai.client.inference.operation.input_tokens", _TOKEN_BOUNDARIES),
        _bucket_view("gen_ai.client.inference.operation.output_tokens", _TOKEN_BOUNDARIES),
        _bucket_view("gen_ai.client.embeddings.duration", _DURATION_BOUNDARIES),
        _bucket_view("gen_ai.client.embeddings.operation.input_tokens", _TOKEN_BOUNDARIES),
    )


def _sanitize_base_url(url):
    """Return the base URL without user information or query values.

    Client hosts may embed credentials, for example `https://user:password@host`.
    Recording them would leak secrets into telemetry, so the user information
    and the query string are dropped before emitting `ollama.request.base_url`.
    """
    parts = urlsplit(url)
    netloc = f"{parts.hostname}:{parts.port}" if parts.port is not None else parts.hostname or ""
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _metric_attributes(operation, request_model, response_model, host, port, error_type=None):
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
    if error_type:
        attributes["error.type"] = error_type
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


def run_chat(client, base_url, *, expect_error=False):
    """Scenario: chat completion with reference implementation.

    When `expect_error` is set the client points at an unreachable server, so
    the SDK call raises after the error attributes, the exception event, the
    duration, and the zero-valued token histograms have been recorded.
    """
    label = "chat failure (unreachable server)" if expect_error else "basic chat completion (reference implementation)"
    print(f"  [chat] {label}")
    request_model = "llama3.2"
    host, port = mock_server_host_port(base_url)
    # One options object handed to the SDK call; the ollama.request.* and
    # gen_ai.request.* span attributes read their values from it.
    request_options = {
        "num_predict": 100,
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
        "frequency_penalty": 1.0,
        "presence_penalty": 0.5,
        "stop": ["\n\n"],
        "seed": 42,
        "num_ctx": 2048,
        "num_batch": 512,
        "num_gpu": 1,
        "main_gpu": 0,
    }
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "gen_ai.request.temperature": request_options["temperature"],
        "gen_ai.request.top_p": request_options["top_p"],
        "gen_ai.request.top_k": request_options["top_k"],
        "gen_ai.request.frequency_penalty": request_options["frequency_penalty"],
        "gen_ai.request.presence_penalty": request_options["presence_penalty"],
        "gen_ai.request.stop_sequences": request_options["stop"],
        "gen_ai.request.seed": request_options["seed"],
        "ollama.request.base_url": _sanitize_base_url(base_url),
        "ollama.request.num_ctx": request_options["num_ctx"],
        "ollama.request.num_batch": request_options["num_batch"],
        "ollama.request.num_gpu": request_options["num_gpu"],
        "ollama.request.main_gpu": request_options["main_gpu"],
    }
    # Ollama uses negative num_predict values as sentinels (-1 requests
    # unlimited generation), so gen_ai.request.max_tokens is only recorded
    # when the option is a non-negative token limit.
    if request_options["num_predict"] >= 0:
        span_attributes["gen_ai.request.max_tokens"] = request_options["num_predict"]
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
    content = None
    with _reference_tracer.start_as_current_span(
        "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        try:
            resp = client.chat(
                model=request_model,
                messages=messages,
                stream=False,
                options=request_options,
            )
        except Exception as exc:
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = _metric_attributes("chat", request_model, None, host, port, error_type)
            _inference_duration.record(elapsed, metric_attributes)
            _record_inference_usage(None, None, metric_attributes)
            reference_event_logger().emit(
                event_name="gen_ai.client.inference.exception",
                severity_number=SeverityNumber.WARN,
                body="Inference operation failed",
                attributes={
                    "exception.type": error_type,
                    "exception.message": str(exc),
                    "exception.stacktrace": traceback.format_exc(),
                },
            )
            raise
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
            "gen_ai.request.temperature": request_options["temperature"],
            "gen_ai.request.top_p": request_options["top_p"],
            "gen_ai.request.top_k": request_options["top_k"],
            "gen_ai.request.frequency_penalty": request_options["frequency_penalty"],
            "gen_ai.request.presence_penalty": request_options["presence_penalty"],
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
        if request_options["num_predict"] >= 0:
            event_attrs["gen_ai.request.max_tokens"] = request_options["num_predict"]
        if resp.model:
            event_attrs["gen_ai.response.model"] = resp.model
        if resp.done_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason]
        if input_tokens is not None:
            event_attrs["gen_ai.usage.input_tokens"] = input_tokens
        if output_tokens is not None:
            event_attrs["gen_ai.usage.output_tokens"] = output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            severity_number=SeverityNumber.DEBUG,
            body="Inference operation details",
            attributes=event_attrs,
        )

    if content:
        print(f"    -> {content[:60]}")


def run_embed(client, base_url, *, expect_error=False):
    """Scenario: embedding generation with reference implementation.

    When `expect_error` is set the client points at an unreachable server, so
    the SDK call raises after the error attributes, the exception event, the
    duration, and the zero-valued input-token histogram have been recorded.
    """
    label = "embeddings failure (unreachable server)" if expect_error else "embedding generation (reference implementation)"
    print(f"  [embeddings] {label}")
    request_model = "nomic-embed-text"
    host, port = mock_server_host_port(base_url)
    request_options = {"num_ctx": 2048}
    span_attributes = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "ollama.request.base_url": _sanitize_base_url(base_url),
        "ollama.request.num_ctx": request_options["num_ctx"],
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    input_text = "Hello, world!"
    input_token_count = 0
    dimension = 0
    with _reference_tracer.start_as_current_span(
        "embeddings nomic-embed-text", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        try:
            resp = client.embed(model=request_model, input=input_text, options=request_options)
        except Exception as exc:
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = _metric_attributes("embeddings", request_model, None, host, port, error_type)
            _embeddings_duration.record(elapsed, metric_attributes)
            _embeddings_input_tokens.record(0, metric_attributes)
            reference_event_logger().emit(
                event_name="gen_ai.client.embeddings.exception",
                severity_number=SeverityNumber.WARN,
                body="Embeddings operation failed",
                attributes={
                    "exception.type": error_type,
                    "exception.message": str(exc),
                    "exception.stacktrace": traceback.format_exc(),
                },
            )
            raise
        elapsed = perf_counter() - started_at
        metric_attributes = _metric_attributes("embeddings", request_model, resp.model, host, port)
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.embeddings:
            dimension = len(resp.embeddings[0])
            span.set_attribute("gen_ai.embeddings.dimension.count", dimension)
        if resp.prompt_eval_count is not None:
            input_token_count = int(resp.prompt_eval_count)
            span.set_attribute("gen_ai.usage.input_tokens", input_token_count)
        if resp.total_duration is not None:
            span.set_attribute("ollama.response.total_duration", int(resp.total_duration))
        if resp.load_duration is not None:
            span.set_attribute("ollama.response.load_duration", int(resp.load_duration))
        _embeddings_duration.record(elapsed, metric_attributes)
        _embeddings_input_tokens.record(input_token_count, metric_attributes)

    print(f"    -> embedding dim: {dimension}")


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel(metric_views=_metric_views())
    # NO instrument() call - reference implementation only

    import ollama

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client, MOCK_BASE_URL)
    run_embed(client, MOCK_BASE_URL)

    # The failure paths point the SDK at a server that accepts no connections:
    # error spans, exception events, and zero-valued metrics are recorded and
    # the SDK exception is re-raised.
    failing_client = ollama.Client(host=UNREACHABLE_BASE_URL)
    for operation in (run_chat, run_embed):
        try:
            operation(failing_client, UNREACHABLE_BASE_URL, expect_error=True)
        except httpx.HTTPError as exc:
            print(f"    -> failed as expected ({type(exc).__name__})")

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
