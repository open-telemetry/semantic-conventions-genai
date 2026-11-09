"""Reference implementation for Ollama.

Exercises: chat (basic, tool call, formatted, and streaming), embeddings, and
text completion (against a scenario-local /api/generate mock) with manual OTel
spans and metrics.
"""

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
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
# user explicitly opts in, per the "Content capture configuration" section
# of docs/gen-ai/gen-ai-spans.md. The scenario configuration enables
# EVENT_ONLY; without an opt-in the events are still emitted, without the
# gen_ai.input.messages and gen_ai.output.messages payloads.
_capture_content = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT", "NO_CONTENT").strip().upper()
if _capture_content not in ("NO_CONTENT", "SPAN_ONLY", "EVENT_ONLY", "SPAN_AND_EVENT"):
    # Unrecognized values fall back to the default capture mode, per the
    # content capture configuration section of docs/gen-ai/gen-ai-spans.md.
    _capture_content = "NO_CONTENT"
# The reference implementation emits content on the operation details events
# only, so SPAN_ONLY behaves like NO_CONTENT here.
_record_event_messages = _capture_content in ("EVENT_ONLY", "SPAN_AND_EVENT")

# gen_ai.tool.definitions is opt-in on the inference span: tool schemas can
# be large and may contain sensitive information, and the content capture
# setting does not govern schema capture, per the attribute's registry note.
# The scenario configuration enables the opt-in so the conformance runner can
# assert the definitions are recorded.
_capture_tool_definitions = (
    os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_TOOL_DEFINITIONS", "").strip().lower() == "true"
)

# The ollama SDK raises ollama.ResponseError when the server reports an error
# status, a builtin ConnectionError on connection failures, and httpx
# exceptions for other transport failures; every failure keeps the same error
# recording and re-raise.
_SDK_FAILURES = (httpx.HTTPError, ConnectionError, ollama.ResponseError)

# Explicit bucket boundaries recommended by docs/gen-ai/client-inference.md,
# docs/gen-ai/client-embeddings.md, and docs/gen-ai/gen-ai-token-metrics.md
# for the duration, streaming chunk, and per-operation token histograms.
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
_time_to_first_chunk = _reference_meter.create_histogram(
    "gen_ai.client.inference.time_to_first_chunk",
    unit="s",
    description="Time from the start of a logical inference operation to the first chunk in its streaming response.",
)
_time_per_output_chunk = _reference_meter.create_histogram(
    "gen_ai.client.inference.time_per_output_chunk",
    unit="s",
    description="Time per output chunk, recorded for each chunk received after the first one.",
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
        _bucket_view("gen_ai.client.inference.time_to_first_chunk", _DURATION_BOUNDARIES),
        _bucket_view("gen_ai.client.inference.time_per_output_chunk", _DURATION_BOUNDARIES),
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


class _GenerateMockHandler(BaseHTTPRequestHandler):
    """Serve a canned /api/generate response.

    The shared conformance mock server implements /api/chat and /api/embed
    only, so the text completion demonstration serves /api/generate from this
    in-process HTTP server with a deterministic response, following the
    scenario-local mock technique of reference/scenarios/gemini-live.
    """

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:00Z",
                "response": "Hello!",
                "done": True,
                "done_reason": "stop",
                "total_duration": 1000000000,
                "load_duration": 100000000,
                "prompt_eval_count": 42,
                "eval_count": 17,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Silence per-request stderr output; the scenario prints its own lines.
        return


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
            # A finish reason is expected for every generation; the registry
            # fallback reports "error" when the response omits it.
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason] if resp.done_reason else ["error"])
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
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason] if resp.done_reason else ["error"]
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
    tools as `gen_ai.tool.definitions`, an opt-in attribute recorded only when
    tool-definition capture is enabled; the operation details event records
    the model's answer as `tool_call` parts of the output message, keeping any
    text of the same response as an independent part. Ollama tool calls carry
    no identifier, which the output message parts permit.
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
        "ollama.request.base_url": _sanitize_base_url(base_url),
        "ollama.request.num_ctx": request_options["num_ctx"],
        "ollama.request.num_batch": request_options["num_batch"],
        "ollama.request.num_gpu": request_options["num_gpu"],
        "ollama.request.main_gpu": request_options["main_gpu"],
    }
    # gen_ai.tool.definitions is opt-in: tool schemas may be large or
    # sensitive, so they are only recorded when explicitly enabled.
    if _capture_tool_definitions:
        span_attributes["gen_ai.tool.definitions"] = tool_definitions
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
            # A finish reason is expected for every generation; the registry
            # fallback reports "error" when the response omits it.
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason] if resp.done_reason else ["error"])
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

            # A response can carry text and tool calls at the same time, so
            # both are captured as independent parts of the output message.
            if resp.message.content:
                output_parts.append({"type": "text", "content": resp.message.content})
            for call in resp.message.tool_calls or []:
                # Ollama tool calls carry no identifier, which the output
                # message parts permit.
                output_parts.append(
                    {
                        "type": "tool_call",
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }
                )
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
            if _capture_tool_definitions:
                event_attrs["gen_ai.tool.definitions"] = tool_definitions
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
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason] if resp.done_reason else ["error"]
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


def run_chat_formatted(client, base_url):
    """Scenario: chat completion requesting JSON output.

    The request passes `format="json"`, so the span and the operation details
    event carry `gen_ai.output.type = "json"`, per the conditionally required
    `gen_ai.output.type` attribute for requests that include an output format.
    """
    print("  [chat] formatted JSON completion (reference implementation)")
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
        "seed": 45,
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
        "gen_ai.output.type": "json",
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
        {"role": "user", "content": "Reply with a JSON object."},
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
                format="json",
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
            # A finish reason is expected for every generation; the registry
            # fallback reports "error" when the response omits it.
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason] if resp.done_reason else ["error"])
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
                "gen_ai.output.type": "json",
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
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason] if resp.done_reason else ["error"]
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


def run_chat_streaming(client, base_url):
    """Scenario: streaming chat completion with reference implementation.

    The request is made with `stream=True`, so the span carries
    `gen_ai.request.stream` and, once the first chunk with content arrives,
    `gen_ai.response.time_to_first_chunk`. The `time_to_first_chunk` and
    `time_per_output_chunk` histograms are recorded from the arrival times of
    the content chunks, and the usage counts and the native Ollama timings
    are read from the final chunk, which carries them like a non-streaming
    response body.
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
        chunk_times = []
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
                    # A chunk is a decoded stream event carrying new,
                    # non-empty output, per the time_to_first_chunk note.
                    chunk_times.append(perf_counter())
                    content_parts.append(chunk.message.content)
                if chunk.done:
                    final_chunk = chunk
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.set_attribute("gen_ai.response.finish_reasons", ["error"])
            if chunk_times:
                # A chunk arrived before the failure, so the measured latency
                # to it is preserved on the failed span; it stays unset only
                # when no chunk was received.
                span.set_attribute("gen_ai.response.time_to_first_chunk", chunk_times[0] - started_at)
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
            # No chunk was received, so time_to_first_chunk and the streaming
            # chunk histograms stay unset, per their requirements.
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
            first_chunk_at = chunk_times[0] if chunk_times else None
            if first_chunk_at is not None:
                # Time from the start of the logical operation, before the
                # request is made, to the first chunk fully received by the
                # client, before application processing.
                span.set_attribute("gen_ai.response.time_to_first_chunk", first_chunk_at - started_at)
            if final_chunk is not None:
                if final_chunk.model:
                    span.set_attribute("gen_ai.response.model", final_chunk.model)
                    response_model = final_chunk.model
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
            # A finish reason is expected for every generation; the registry
            # fallback reports "error" when the stream ends without one.
            if final_chunk is not None and final_chunk.done_reason:
                finish_reasons = [final_chunk.done_reason]
            else:
                finish_reasons = ["error"]
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)

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
            if chunk_times:
                # The streaming chunk histograms follow the chunk definition
                # of gen_ai.response.time_to_first_chunk and are only
                # recorded when the stream delivered content chunks.
                _time_to_first_chunk.record(chunk_times[0] - started_at, metric_attributes)
                for previous, current in pairwise(chunk_times):
                    _time_per_output_chunk.record(current - previous, metric_attributes)

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
            if first_chunk_at is not None:
                event_attrs["gen_ai.response.time_to_first_chunk"] = first_chunk_at - started_at
            if response_model:
                event_attrs["gen_ai.response.model"] = response_model
            event_attrs["gen_ai.response.finish_reasons"] = finish_reasons
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
    # One options object handed to the SDK call; the ollama.request.* span
    # attributes read their values from it. The embeddings refinement records
    # num_batch, num_gpu, and main_gpu with the same conditions as the
    # inference refinement, because client.embed accepts the same options.
    request_options = {
        "num_ctx": 2048,
        "num_batch": 512,
        "num_gpu": 1,
        "main_gpu": 0,
    }
    span_attributes = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "ollama.request.base_url": _sanitize_base_url(base_url),
        "ollama.request.num_ctx": request_options["num_ctx"],
        "ollama.request.num_batch": request_options["num_batch"],
        "ollama.request.num_gpu": request_options["num_gpu"],
        "ollama.request.main_gpu": request_options["main_gpu"],
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


def run_text_completion():
    """Scenario: text completion with reference implementation.

    The Ollama SDK exposes `client.generate` for the `/api/generate` endpoint,
    which maps to a `gen_ai.client.inference` span with
    `gen_ai.operation.name = "text_completion"`. The shared conformance mock
    server implements `/api/chat` and `/api/embed` only, so this scenario
    serves a canned `/api/generate` response from an in-process HTTP server
    and makes a real SDK call against it.
    """
    print("  [generate] text completion (reference implementation, local /api/generate mock)")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GenerateMockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_url = f"http://127.0.0.1:{port}"
        client = ollama.Client(host=base_url)
        request_model = "llama3.2"
        request_options = {
            "num_ctx": 2048,
            "num_batch": 512,
            "num_gpu": 1,
            "main_gpu": 0,
        }
        prompt = "Say hello."
        span_attributes = {
            "gen_ai.operation.name": "text_completion",
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": request_model,
            "ollama.request.base_url": _sanitize_base_url(base_url),
            "ollama.request.num_ctx": request_options["num_ctx"],
            "ollama.request.num_batch": request_options["num_batch"],
            "ollama.request.num_gpu": request_options["num_gpu"],
            "ollama.request.main_gpu": request_options["main_gpu"],
            "server.address": "127.0.0.1",
            "server.port": port,
        }
        input_tokens = None
        output_tokens = None
        response_model = None
        content = None
        with _reference_tracer.start_as_current_span(
            "text_completion llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            started_at = perf_counter()
            resp = client.generate(model=request_model, prompt=prompt, options=request_options)
            elapsed = perf_counter() - started_at
            if resp.model:
                span.set_attribute("gen_ai.response.model", resp.model)
                response_model = resp.model
            # A finish reason is expected for every generation; the registry
            # fallback reports "error" when the response omits it.
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason] if resp.done_reason else ["error"])
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
                "gen_ai.operation.name": "text_completion",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
            }
            if response_model:
                metric_attributes["gen_ai.response.model"] = response_model
            metric_attributes["server.address"] = "127.0.0.1"
            metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
            _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
            if input_tokens:
                _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
            if output_tokens:
                _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})

            content = resp.response
            event_attrs = {
                "gen_ai.operation.name": "text_completion",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "gen_ai.response.finish_reasons": [resp.done_reason] if resp.done_reason else ["error"],
            }
            if _record_event_messages:
                event_attrs["gen_ai.input.messages"] = [
                    {"role": "user", "parts": [{"type": "text", "content": prompt}]}
                ]
                event_attrs["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": content}],
                    }
                ]
            if resp.model:
                event_attrs["gen_ai.response.model"] = resp.model
            if input_tokens is not None:
                event_attrs["gen_ai.usage.input_tokens"] = input_tokens
            if output_tokens is not None:
                event_attrs["gen_ai.usage.output_tokens"] = output_tokens
            event_attrs["server.address"] = "127.0.0.1"
            event_attrs["server.port"] = port
            reference_event_logger().emit(
                event_name="gen_ai.client.inference.operation.details",
                severity_number=SeverityNumber.DEBUG,
                body="Inference operation details",
                attributes=event_attrs,
            )
    finally:
        server.shutdown()
        server.server_close()
    if content:
        print(f"    -> {content[:60]}")


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel(metric_views=_metric_views())
    # NO instrument() call - reference implementation only

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client, MOCK_BASE_URL)
    run_chat_with_tools(client, MOCK_BASE_URL)
    run_chat_formatted(client, MOCK_BASE_URL)
    run_chat_streaming(client, MOCK_BASE_URL)
    run_embed(client, MOCK_BASE_URL)
    run_text_completion()

    # The failure paths point the SDK at a server that accepts no
    # connections: error spans, exception events, and zero-valued metrics are
    # recorded and the SDK exception is re-raised.
    failing_client = ollama.Client(host=UNREACHABLE_BASE_URL)
    for operation in (run_chat, run_embed):
        _require_failure(operation, failing_client, UNREACHABLE_BASE_URL)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
