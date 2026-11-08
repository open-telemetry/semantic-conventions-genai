"""Reference implementation for Ollama.

Exercises: chat (basic, tool call, and streaming) and embeddings
against a mock Ollama server, with manual OTel spans and metrics.
"""

import os
import traceback
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx
import ollama
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

# Message content is only recorded on the operation details events when the
# user explicitly opts in, per the "Recording content on attributes" section
# of docs/gen-ai/gen-ai-spans.md. The scenario configuration enables
# EVENT_ONLY; without an opt-in the events are still emitted, without the
# gen_ai.input.messages and gen_ai.output.messages payloads.
_capture_content = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT")
_record_event_messages = _capture_content in ("EVENT_ONLY", "SPAN_AND_EVENT")

# The ollama SDK raises ollama.ResponseError when the server reports an error
# status, a builtin ConnectionError on connection failures, and httpx
# exceptions for other transport failures; every failure keeps the same error
# recording and re-raise.
_SDK_FAILURES = (httpx.HTTPError, ConnectionError, ollama.ResponseError)

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
    # urlsplit().hostname strips the brackets of an IPv6 literal, but the
    # authority requires them, so they are restored before the port is added.
    host = parts.hostname or ""
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _require_failure(operation, client, base_url):
    """Run `operation` against `base_url`, which accepts no connections.

    The failure path is only exercised when the SDK call actually raises: a
    silent success would leave the error span, the exception event, and the
    zero-valued metrics unrecorded, so the run fails instead of continuing.
    """
    try:
        operation(client, base_url, expect_error=True)
    except _SDK_FAILURES as exc:
        print(f"    -> failed as expected ({type(exc).__name__})")
        return exc
    raise RuntimeError(f"{operation.__name__} unexpectedly succeeded against {base_url}")


def run_chat(client, base_url, *, expect_error=False):
    """Scenario: chat completion with reference implementation.

    When `expect_error` is set the client points at an unreachable server, so
    the SDK call raises after the error attributes, the exception event, the
    duration, and the zero-valued token histograms have been recorded; the
    failed span also carries `gen_ai.response.finish_reasons = ["error"]`,
    per the finish-reason guidance for operations that fail before any
    generation exists. The exception is re-raised once the span has closed, so
    the OTel SDK does not add exception attributes the GenAI registry does not
    define.
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
    failure = None
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
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            # The operation ended before any generation existed, so the
            # finish-reason guidance requires an "error" entry.
            span.set_attribute("gen_ai.response.finish_reasons", ["error"])
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "error.type": error_type,
            }
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            # The per-operation histograms are recorded for every operation,
            # so a failure records zero tokens.
            _operation_input_tokens.record(0, metric_attributes)
            _operation_output_tokens.record(0, metric_attributes)
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
        else:
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

            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
            }
            if response_model:
                metric_attributes["gen_ai.response.model"] = response_model
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            # The per-operation histograms are recorded for every inference
            # operation: the value is the token count returned by the
            # provider, or 0 when the response contains no token usage.
            _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
            _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
            # Ollama reports no per-modality token breakdown, so every counter
            # point goes to the unknown modality, and the usage counters are
            # only incremented for known positive counts.
            if input_tokens:
                _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
            if output_tokens:
                _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})

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
            }
            if _record_event_messages:
                event_attrs["gen_ai.input.messages"] = [
                    {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
                ]
                event_attrs["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": content}],
                    }
                ]
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

    if failure is not None:
        raise failure
    if content:
        print(f"    -> {content[:60]}")


def run_chat_with_tools(client, base_url):
    """Scenario: chat completion offering a tool and receiving a tool call.

    The request offers a weather tool through the SDK `tools` argument, and
    the mock server answers with a tool call. The span records the offered
    tools as `gen_ai.tool.definitions`; the operation details event records
    the model's answer as `tool_call` parts of the output message. Ollama
    tool calls carry no identifier, which the output message parts permit.
    """
    print("  [chat] tool call (reference implementation)")
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
        "seed": 43,
        "num_ctx": 2048,
        "num_batch": 512,
        "num_gpu": 1,
        "main_gpu": 0,
    }
    # The ollama SDK takes OpenAI-style tool definitions, while
    # gen_ai.tool.definitions records the flat semantic-convention shape.
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a given location.",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        }
    ]
    tool_definitions = [
        {
            "type": tool["type"],
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "parameters": tool["function"]["parameters"],
        }
        for tool in tools
    ]
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
        "gen_ai.tool.definitions": tool_definitions,
        "ollama.request.base_url": _sanitize_base_url(base_url),
        "ollama.request.num_ctx": request_options["num_ctx"],
        "ollama.request.num_batch": request_options["num_batch"],
        "ollama.request.num_gpu": request_options["num_gpu"],
        "ollama.request.main_gpu": request_options["main_gpu"],
    }
    if request_options["num_predict"] >= 0:
        span_attributes["gen_ai.request.max_tokens"] = request_options["num_predict"]
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the weather in Paris?"},
    ]
    input_tokens = None
    output_tokens = None
    response_model = None
    output_parts = []
    failure = None
    with _reference_tracer.start_as_current_span(
        "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        try:
            resp = client.chat(
                model=request_model,
                messages=messages,
                tools=tools,
                stream=False,
                options=request_options,
            )
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.set_attribute("gen_ai.response.finish_reasons", ["error"])
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "error.type": error_type,
            }
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            _operation_input_tokens.record(0, metric_attributes)
            _operation_output_tokens.record(0, metric_attributes)
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
        else:
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

            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
            }
            if response_model:
                metric_attributes["gen_ai.response.model"] = response_model
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
            _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
            if input_tokens:
                _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
            if output_tokens:
                _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})

            if resp.message.tool_calls:
                for call in resp.message.tool_calls:
                    part = {
                        "type": "tool_call",
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }
                    # Ollama tool calls carry no identifier; the id is only
                    # recorded when the SDK exposes one.
                    call_id = getattr(call, "id", None)
                    if call_id:
                        part["id"] = call_id
                    output_parts.append(part)
            else:
                output_parts = [{"type": "text", "content": resp.message.content}]
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
                "gen_ai.tool.definitions": tool_definitions,
            }
            if _record_event_messages:
                event_attrs["gen_ai.input.messages"] = [
                    {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
                ]
                event_attrs["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": output_parts,
                    }
                ]
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

    if failure is not None:
        raise failure
    for part in output_parts:
        if part["type"] == "tool_call":
            print(f"    -> tool call: {part['name']}({part['arguments']})")
        elif part["type"] == "text" and part["content"]:
            print(f"    -> {part['content'][:60]}")


def run_chat_streaming(client, base_url):
    """Scenario: streaming chat completion with reference implementation.

    The request is made with `stream=True`, so the span carries
    `gen_ai.request.stream` and, once the first chunk with content arrives,
    `gen_ai.response.time_to_first_chunk`. The usage counts and the native
    Ollama timings are read from the final chunk, which carries them like a
    non-streaming response body.
    """
    print("  [chat] streaming completion (reference implementation)")
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
        "seed": 44,
        "num_ctx": 2048,
        "num_batch": 512,
        "num_gpu": 1,
        "main_gpu": 0,
    }
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "gen_ai.request.stream": True,
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
    content_parts = []
    failure = None
    with _reference_tracer.start_as_current_span(
        "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        first_chunk_at = None
        final_chunk = None
        try:
            stream = client.chat(
                model=request_model,
                messages=messages,
                stream=True,
                options=request_options,
            )
            for chunk in stream:
                if chunk.message and chunk.message.content:
                    if first_chunk_at is None:
                        # A chunk is a decoded stream event carrying new,
                        # non-empty output, per the time_to_first_chunk note.
                        first_chunk_at = perf_counter()
                    content_parts.append(chunk.message.content)
                if chunk.done:
                    final_chunk = chunk
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.set_attribute("gen_ai.response.finish_reasons", ["error"])
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "error.type": error_type,
            }
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            # No chunk was received, so time_to_first_chunk stays unset, per
            # its requirement.
            _operation_input_tokens.record(0, metric_attributes)
            _operation_output_tokens.record(0, metric_attributes)
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
        else:
            elapsed = perf_counter() - started_at
            if first_chunk_at is not None:
                # Time from the start of the logical operation, before the
                # request is made, to the first chunk fully received by the
                # client, before application processing.
                span.set_attribute("gen_ai.response.time_to_first_chunk", first_chunk_at - started_at)
            if final_chunk is not None:
                if final_chunk.model:
                    span.set_attribute("gen_ai.response.model", final_chunk.model)
                    response_model = final_chunk.model
                if final_chunk.done_reason:
                    span.set_attribute("gen_ai.response.finish_reasons", [final_chunk.done_reason])
                if final_chunk.prompt_eval_count is not None:
                    input_tokens = int(final_chunk.prompt_eval_count)
                    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                if final_chunk.eval_count is not None:
                    output_tokens = int(final_chunk.eval_count)
                    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                if final_chunk.total_duration is not None:
                    span.set_attribute("ollama.response.total_duration", int(final_chunk.total_duration))
                if final_chunk.load_duration is not None:
                    span.set_attribute("ollama.response.load_duration", int(final_chunk.load_duration))

            metric_attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
            }
            if response_model:
                metric_attributes["gen_ai.response.model"] = response_model
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
            _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
            if input_tokens:
                _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
            if output_tokens:
                _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})

            content = "".join(content_parts)
            event_attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "gen_ai.request.stream": True,
                "gen_ai.request.temperature": request_options["temperature"],
                "gen_ai.request.top_p": request_options["top_p"],
                "gen_ai.request.top_k": request_options["top_k"],
                "gen_ai.request.frequency_penalty": request_options["frequency_penalty"],
                "gen_ai.request.presence_penalty": request_options["presence_penalty"],
                "gen_ai.request.stop_sequences": request_options["stop"],
                "gen_ai.request.seed": request_options["seed"],
            }
            if _record_event_messages:
                event_attrs["gen_ai.input.messages"] = [
                    {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
                ]
                event_attrs["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": content}],
                    }
                ]
            if request_options["num_predict"] >= 0:
                event_attrs["gen_ai.request.max_tokens"] = request_options["num_predict"]
            if response_model:
                event_attrs["gen_ai.response.model"] = response_model
            if final_chunk is not None and final_chunk.done_reason:
                event_attrs["gen_ai.response.finish_reasons"] = [final_chunk.done_reason]
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

    if failure is not None:
        raise failure
    if content_parts:
        print(f"    -> {''.join(content_parts)[:60]}")


def run_embed(client, base_url, *, expect_error=False):
    """Scenario: embedding generation with reference implementation.

    When `expect_error` is set the client points at an unreachable server, so
    the SDK call raises after the error attributes, the exception event, the
    duration, and the zero-valued input-token histogram have been recorded. The
    exception is re-raised once the span has closed, so the OTel SDK does not
    add exception attributes the GenAI registry does not define.
    """
    label = (
        "embeddings failure (unreachable server)" if expect_error else "embedding generation (reference implementation)"
    )
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
    failure = None
    with _reference_tracer.start_as_current_span(
        "embeddings nomic-embed-text", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        started_at = perf_counter()
        try:
            resp = client.embed(model=request_model, input=input_text, options=request_options)
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.set_status(StatusCode.ERROR, str(exc))
            metric_attributes = {
                "gen_ai.operation.name": "embeddings",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "error.type": error_type,
            }
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
            _embeddings_duration.record(elapsed, metric_attributes)
            # The input-token histogram is recorded for every operation, so
            # a failure records zero tokens.
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
        else:
            elapsed = perf_counter() - started_at
            metric_attributes = {
                "gen_ai.operation.name": "embeddings",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
            }
            if resp.model:
                metric_attributes["gen_ai.response.model"] = resp.model
                span.set_attribute("gen_ai.response.model", resp.model)
            if host:
                metric_attributes["server.address"] = host
            if port is not None:
                metric_attributes["server.port"] = port
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

    if failure is not None:
        raise failure
    print(f"    -> embedding dim: {dimension}")


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel(metric_views=_metric_views())
    # NO instrument() call - reference implementation only

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client, MOCK_BASE_URL)
    run_chat_with_tools(client, MOCK_BASE_URL)
    run_chat_streaming(client, MOCK_BASE_URL)
    run_embed(client, MOCK_BASE_URL)

    # The failure paths point the SDK at a server that accepts no
    # connections: error spans, exception events, and zero-valued metrics are
    # recorded and the SDK exception is re-raised.
    failing_client = ollama.Client(host=UNREACHABLE_BASE_URL)
    for operation in (run_chat, run_embed):
        _require_failure(operation, failing_client, UNREACHABLE_BASE_URL)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
