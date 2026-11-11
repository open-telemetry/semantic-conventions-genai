"""Reference implementation for Ollama.

Exercises: chat (basic, tool call, formatted, streaming, and the span content
capture modes), embeddings, and text completion (against a scenario-local
/api/generate mock), plus a cached prompt-token chat, a streaming tool call,
and a mid-stream failure against scenario-local /api/chat mocks, with manual
OTel spans and metrics.
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

# Message content capture is configured through
# OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT; see _capture_mode below. The
# scenario configuration enables EVENT_ONLY, so the operation details events
# carry the gen_ai.input.messages and gen_ai.output.messages payloads, and
# the span capture modes are exercised with per-call overrides.

# gen_ai.tool.definitions is opt-in on the inference span: tool schemas can
# be large and may contain sensitive information, and the content capture
# setting does not govern schema capture, per the attribute's registry note.
# The scenario configuration enables the opt-in so the conformance runner can
# assert the definitions are recorded.
_capture_tool_definitions = (
    os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_TOOL_DEFINITIONS", "").strip().lower() == "true"
)

# The weather tool used by the tool-call scenarios: the ollama SDK takes
# OpenAI-style tool definitions, while gen_ai.tool.definitions records the
# flat semantic-convention shape. Both scenarios share the same definitions,
# so the recorded values stay identical.
_WEATHER_TOOLS = [
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
_WEATHER_TOOL_DEFINITIONS = [
    {
        "type": tool["type"],
        "name": tool["function"]["name"],
        "description": tool["function"]["description"],
        "parameters": tool["function"]["parameters"],
    }
    for tool in _WEATHER_TOOLS
]

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
_cache_read_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.cache_read.input_tokens",
    unit="{token}",
    description="The number of input tokens served from a provider-managed cache.",
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


def _capture_mode():
    """Return the configured message-content capture mode.

    Message content is only recorded when the user explicitly opts in, per
    the "Content capture configuration" section of docs/gen-ai/gen-ai-spans.md.
    Unrecognized values fall back to the default NO_CONTENT mode.
    """
    mode = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT", "NO_CONTENT").strip().upper()
    if mode not in ("NO_CONTENT", "SPAN_ONLY", "EVENT_ONLY", "SPAN_AND_EVENT"):
        return "NO_CONTENT"
    return mode


def _record_span_messages(mode):
    """Whether the capture mode records the input and output messages on the span."""
    return mode in ("SPAN_ONLY", "SPAN_AND_EVENT")


def _record_event_messages(mode):
    """Whether the capture mode records the input and output messages on the event."""
    return mode in ("EVENT_ONLY", "SPAN_AND_EVENT")


def _chunk_has_output(message):
    """Whether a stream chunk carries new, non-empty output.

    The chunk definition of gen_ai.response.time_to_first_chunk covers every
    decoded stream event with new output: text, reasoning, and tool-call
    names or arguments. Roles, usage, and end-of-stream markers do not count.
    """
    if message is None:
        return False
    if getattr(message, "content", None):
        return True
    if getattr(message, "thinking", None):
        return True
    for call in getattr(message, "tool_calls", None) or []:
        function = getattr(call, "function", None)
        if function is not None and (getattr(function, "name", None) or getattr(function, "arguments", None)):
            return True
    return False


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


class _StreamingToolsMockHandler(BaseHTTPRequestHandler):
    """Serve a canned /api/chat tool-call stream.

    The streaming tool-call demonstration serves an ndjson chunk sequence
    from this in-process HTTP server with a deterministic tool call,
    following the scenario-local mock technique of reference/scenarios/gemini-live:
    the first chunk carries only the role, the second reasoning, the third
    the tool call, and the final chunk the done marker with the usage counts.
    """

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        chunks = [
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:00Z",
                "message": {"role": "assistant", "content": ""},
                "done": False,
            },
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:01Z",
                "message": {"role": "assistant", "content": "", "thinking": "Thinking about the weather in Paris."},
                "done": False,
            },
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:02Z",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "get_weather", "arguments": {"location": "Paris"}}}],
                },
                "done": False,
            },
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:03Z",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "total_duration": 1000000000,
                "load_duration": 100000000,
                "prompt_eval_count": 11,
                "eval_count": 5,
            },
        ]
        body = ("".join(json.dumps(chunk) + "\n" for chunk in chunks)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Silence per-request stderr output; the scenario prints its own lines.
        return


class _StreamingFailureMockHandler(BaseHTTPRequestHandler):
    """Serve a /api/chat stream that drops mid-stream.

    The response promises one ndjson chunk more than it delivers, then
    closes the connection, so the SDK raises a transport error after a chunk
    arrived: the failure path where the stream delivered output but did not
    complete.
    """

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        first_chunk = {
            "model": "llama3.2",
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": "Hel"},
            "done": False,
        }
        first = (json.dumps(first_chunk) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        # The content length promises a second chunk that is never delivered.
        self.send_header("Content-Length", str(len(first) + 64))
        self.end_headers()
        self.wfile.write(first)
        self.wfile.flush()
        # Closing the connection with the promised body undelivered makes
        # the SDK raise a transport error mid-stream.
        self.close_connection = True

    def log_message(self, format, *args):
        # Silence per-request stderr output; the scenario prints its own lines.
        return


class _CachedPromptChatMockHandler(BaseHTTPRequestHandler):
    """Serve a canned non-streaming /api/chat response with cached prompt tokens.

    The shared conformance mock server does not report the server-side
    prompt_eval_cached_count field, so the cached prompt-token demonstration
    serves /api/chat from this in-process HTTP server: 23 of the 100 prompt
    tokens were served from the prompt cache, a subset relationship the
    gen_ai.usage.cache_read.input_tokens mapping relies on.
    """

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "model": "llama3.2",
                "created_at": "2026-01-01T00:00:00Z",
                "message": {"role": "assistant", "content": "Hello!"},
                "done": True,
                "done_reason": "stop",
                "total_duration": 1000000000,
                "load_duration": 100000000,
                "prompt_eval_count": 100,
                "prompt_eval_cached_count": 23,
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


class _CacheReadCaptureTransport(httpx.BaseTransport):
    """Capture prompt_eval_cached_count from the raw /api/chat response.

    ollama-python parses responses into models that do not declare the
    server's prompt_eval_cached_count field, so the field is silently dropped
    (ollama/ollama-python#773). This transport wraps the HTTP transport and
    reads the field from the raw response, as an instrumentation with raw API
    access would, for mapping to gen_ai.usage.cache_read.input_tokens. The
    SDK forwards keyword arguments to its httpx client, so the transport is
    injected through the supported transport argument. Streamed responses
    are skipped: the SDK reads a non-streaming response into memory anyway,
    but buffering a streamed response would delay every chunk and distort the
    time-to-first-chunk timing. Once an SDK release exposes the field, the
    transport is removed and the value is read from the parsed response.
    """

    def __init__(self, transport):
        self._transport = transport
        self.cached_prompt_tokens = None

    def handle_request(self, request):
        response = self._transport.handle_request(request)
        if request.url.path != "/api/chat":
            return response
        payload = json.loads(request.content)
        if payload.get("stream"):
            # A buffered read would delay streamed chunks, so streamed
            # responses are not captured.
            return response
        body = json.loads(response.read())
        cached = body.get("prompt_eval_cached_count")
        if cached:
            self.cached_prompt_tokens = int(cached)
        return response


def run_chat(client, base_url, *, expect_error=False, capture_mode=None, seed=42):
    """Scenario: chat completion with reference implementation.

    When `expect_error` is set the client points at an unreachable server, so
    the SDK call raises after the error attributes, the exception event, the
    duration, and the zero-valued token histograms have been recorded; the
    failed span also carries `gen_ai.response.finish_reasons = ["error"]`,
    per the finish-reason guidance for operations that fail before any
    generation exists. The exception is re-raised once the span has closed, so
    the OTel SDK does not add exception attributes the GenAI registry does not
    define. The `seed` option and the `capture_mode` override parameterize the
    run for the conformance assertions and exercise the span content capture
    modes.
    """
    if expect_error:
        label = "chat failure (unreachable server)"
    elif capture_mode is not None:
        label = f"chat completion with {capture_mode} content capture"
    else:
        label = "basic chat completion (reference implementation)"
    print(f"  [chat] {label}")
    mode = _capture_mode() if capture_mode is None else capture_mode
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
        "seed": seed,
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
    # Message content is recorded on the span when the SPAN_ONLY or
    # SPAN_AND_EVENT capture mode is enabled, per the content capture
    # configuration section of docs/gen-ai/gen-ai-spans.md.
    if _record_span_messages(mode):
        span_attributes["gen_ai.input.messages"] = [
            {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
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
            if _record_span_messages(mode):
                span.set_attribute(
                    "gen_ai.output.messages",
                    [{"role": "assistant", "parts": [{"type": "text", "content": content}]}],
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
            if _record_event_messages(mode):
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
    mode = _capture_mode()
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
    tools = _WEATHER_TOOLS
    tool_definitions = _WEATHER_TOOL_DEFINITIONS
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
    # Message content is recorded on the span when the SPAN_ONLY or
    # SPAN_AND_EVENT capture mode is enabled, per the content capture
    # configuration section of docs/gen-ai/gen-ai-spans.md.
    if _record_span_messages(mode):
        span_attributes["gen_ai.input.messages"] = [
            {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
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
            if _record_span_messages(mode):
                span.set_attribute("gen_ai.output.messages", [{"role": "assistant", "parts": output_parts}])
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
            if _record_event_messages(mode):
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
    mode = _capture_mode()
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
    # Message content is recorded on the span when the SPAN_ONLY or
    # SPAN_AND_EVENT capture mode is enabled, per the content capture
    # configuration section of docs/gen-ai/gen-ai-spans.md.
    if _record_span_messages(mode):
        span_attributes["gen_ai.input.messages"] = [
            {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
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
            if _record_span_messages(mode):
                span.set_attribute(
                    "gen_ai.output.messages",
                    [{"role": "assistant", "parts": [{"type": "text", "content": content}]}],
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
                "gen_ai.output.type": "json",
            }
            if _record_event_messages(mode):
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


def run_chat_streaming(
    client,
    base_url,
    *,
    expect_error=False,
    tools=None,
    seed=44,
    capture_mode=None,
    mock_host=None,
    mock_port=None,
):
    """Scenario: streaming chat completion with reference implementation.

    The request is made with `stream=True`, so the span carries
    `gen_ai.request.stream` and, once the first chunk with output arrives,
    `gen_ai.response.time_to_first_chunk`. A chunk is a decoded stream event
    carrying new, non-empty output - text, reasoning, or tool-call names or
    arguments - per the chunk definition of the generic attribute, so the
    arrival times are taken from every such chunk, not only text. The
    `time_to_first_chunk` and `time_per_output_chunk` histograms are recorded
    from the chunk arrival times, also on a failed stream when a chunk
    arrived, and the usage counts and the native Ollama timings are read from
    the final chunk, which carries them like a non-streaming response body.
    When `tools` is passed the request offers the weather tool and the stream
    answers with reasoning followed by a tool call, recorded as reasoning and
    `tool_call` parts of the output message. The serving model is captured
    from the first chunk that carries it, so a stream that fails mid-stream
    still records gen_ai.response.model, and the output accumulated before
    a mid-stream failure is recorded on the span when span capture is
    enabled and copied to the exception event only when both span and event
    capture are enabled, since the exception event may only copy attributes
    captured on the span, before the exception is re-raised.
    """
    if expect_error:
        label = "streaming failure (connection dropped mid-stream)"
    elif tools:
        label = "streaming tool call"
    else:
        label = "streaming completion"
    print(f"  [chat] {label} (reference implementation)")
    mode = _capture_mode() if capture_mode is None else capture_mode
    request_model = "llama3.2"
    host, port = mock_server_host_port(base_url)
    if mock_host is not None:
        host = mock_host
    if mock_port is not None:
        port = mock_port
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
        "seed": seed,
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
    # gen_ai.tool.definitions is opt-in: tool schemas may be large or
    # sensitive, so they are only recorded when explicitly enabled.
    if tools and _capture_tool_definitions:
        span_attributes["gen_ai.tool.definitions"] = _WEATHER_TOOL_DEFINITIONS
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
    # Message content is recorded on the span when the SPAN_ONLY or
    # SPAN_AND_EVENT capture mode is enabled, per the content capture
    # configuration section of docs/gen-ai/gen-ai-spans.md.
    if _record_span_messages(mode):
        span_attributes["gen_ai.input.messages"] = [
            {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
        ]
    input_tokens = None
    output_tokens = None
    response_model = None
    stream_model = None
    content_parts = []
    thinking_parts = []
    output_tool_calls = []
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
                tools=tools,
                stream=True,
                options=request_options,
            )
            for chunk in stream:
                if getattr(chunk, "model", None):
                    # The first chunk that identifies the serving model is
                    # kept, so a stream that fails mid-stream still carries
                    # gen_ai.response.model.
                    stream_model = chunk.model
                message = getattr(chunk, "message", None)
                if _chunk_has_output(message):
                    # A chunk is a decoded stream event carrying new,
                    # non-empty output: text, reasoning, or tool-call names
                    # or arguments, per the chunk definition.
                    chunk_times.append(perf_counter())
                    if message.content:
                        content_parts.append(message.content)
                    thinking = getattr(message, "thinking", None)
                    if thinking:
                        thinking_parts.append(thinking)
                    for call in message.tool_calls or []:
                        output_tool_calls.append(
                            {
                                "type": "tool_call",
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            }
                        )
                if chunk.done:
                    final_chunk = chunk
        except _SDK_FAILURES as exc:
            failure = exc
            elapsed = perf_counter() - started_at
            error_type = type(exc).__name__
            span.set_attribute("error.type", error_type)
            span.set_attribute("gen_ai.response.finish_reasons", ["error"])
            if stream_model:
                # The stream identified the serving model before it failed,
                # so the model is preserved on the span and the metrics that
                # carry it on the success path.
                span.set_attribute("gen_ai.response.model", stream_model)
            if chunk_times:
                # A chunk arrived before the failure, so the measured latency
                # to it is preserved on the failed span; it stays unset only
                # when no chunk was received.
                span.set_attribute("gen_ai.response.time_to_first_chunk", chunk_times[0] - started_at)
                # The streaming chunk histograms are recorded whenever a
                # chunk arrived, including on a failed stream, per their
                # requirements. The metric refinement carries no error.type:
                # these points record chunk latencies, not the failure.
                chunk_metric_attributes = {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "ollama",
                    "gen_ai.request.model": request_model,
                }
                if host:
                    chunk_metric_attributes["server.address"] = host
                if port is not None:
                    chunk_metric_attributes["server.port"] = port
                if stream_model:
                    chunk_metric_attributes["gen_ai.response.model"] = stream_model
                _time_to_first_chunk.record(chunk_times[0] - started_at, chunk_metric_attributes)
                for previous, current in pairwise(chunk_times):
                    _time_per_output_chunk.record(current - previous, chunk_metric_attributes)
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
            if stream_model:
                metric_attributes["gen_ai.response.model"] = stream_model
            _inference_duration.record(elapsed, metric_attributes)
            # The per-operation histograms are recorded for every operation,
            # so a failure records zero tokens; the streaming chunk
            # histograms above are only recorded when a chunk arrived.
            _operation_input_tokens.record(0, metric_attributes)
            _operation_output_tokens.record(0, metric_attributes)
            # The stream may have delivered output before it failed, so the
            # partial output is recorded on the span when span capture is
            # enabled and copied to the exception event when both span and
            # event capture are enabled, before the exception is re-raised;
            # a failure that produced no output leaves
            # gen_ai.output.messages unset.
            partial_parts = []
            partial_content = "".join(content_parts)
            if partial_content:
                partial_parts.append({"type": "text", "content": partial_content})
            partial_reasoning = "".join(thinking_parts)
            if partial_reasoning:
                partial_parts.append({"type": "reasoning", "content": partial_reasoning})
            partial_parts.extend(output_tool_calls)
            if _record_span_messages(mode) and partial_parts:
                span.set_attribute("gen_ai.output.messages", [{"role": "assistant", "parts": partial_parts}])
            exception_event_attributes = {
                "exception.type": error_type,
                "exception.message": str(exc),
                "exception.stacktrace": traceback.format_exc(),
            }
            if _record_span_messages(mode) and _record_event_messages(mode) and partial_parts:
                # The exception event may only copy attributes captured on
                # the corresponding inference span, so the partial output is
                # included only when both span and event capture are enabled
                # (the SPAN_AND_EVENT mode).
                exception_event_attributes["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": partial_parts,
                    }
                ]
            reference_event_logger().emit(
                event_name="gen_ai.client.inference.exception",
                severity_number=SeverityNumber.WARN,
                body="Inference operation failed",
                attributes=exception_event_attributes,
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
            if response_model is None and stream_model:
                # The final chunk omitted the model, so the one seen first
                # on an intermediate chunk is kept.
                response_model = stream_model
                span.set_attribute("gen_ai.response.model", stream_model)
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
                # recorded when the stream delivered chunks with output.
                _time_to_first_chunk.record(chunk_times[0] - started_at, metric_attributes)
                for previous, current in pairwise(chunk_times):
                    _time_per_output_chunk.record(current - previous, metric_attributes)

            content = "".join(content_parts)
            output_parts = []
            if content:
                output_parts.append({"type": "text", "content": content})
            reasoning = "".join(thinking_parts)
            if reasoning:
                # The reasoning accumulated across chunks is captured as an
                # independent reasoning part of the output message, after the
                # text and before the tool calls.
                output_parts.append({"type": "reasoning", "content": reasoning})
            # The accumulated tool calls are captured as independent parts
            # of the output message, alongside any text of the response.
            output_parts.extend(output_tool_calls)
            if _record_span_messages(mode):
                span.set_attribute("gen_ai.output.messages", [{"role": "assistant", "parts": output_parts}])
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
            if tools and _capture_tool_definitions:
                event_attrs["gen_ai.tool.definitions"] = _WEATHER_TOOL_DEFINITIONS
            if _record_event_messages(mode):
                event_attrs["gen_ai.input.messages"] = [
                    {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
                ]
                event_attrs["gen_ai.output.messages"] = [{"role": "assistant", "parts": output_parts}]
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
    for part in output_tool_calls:
        print(f"    -> tool call: {part['name']}({part['arguments']})")
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
    mode = _capture_mode()
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
        # Message content is recorded on the span when the SPAN_ONLY or
        # SPAN_AND_EVENT capture mode is enabled, per the content capture
        # configuration section of docs/gen-ai/gen-ai-spans.md.
        if _record_span_messages(mode):
            span_attributes["gen_ai.input.messages"] = [
                {"role": "user", "parts": [{"type": "text", "content": prompt}]}
            ]
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
            if _record_span_messages(mode):
                span.set_attribute(
                    "gen_ai.output.messages",
                    [{"role": "assistant", "parts": [{"type": "text", "content": content}]}],
                )
            event_attrs = {
                "gen_ai.operation.name": "text_completion",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "gen_ai.response.finish_reasons": [resp.done_reason] if resp.done_reason else ["error"],
            }
            if _record_event_messages(mode):
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


def run_chat_cached_prompt(seed=50):
    """Scenario: chat completion with a cached prompt-token demonstration.

    The Ollama server reports the number of prompt tokens served from the
    prompt cache as prompt_eval_cached_count, a subset of prompt_eval_count,
    which maps to gen_ai.usage.cache_read.input_tokens. ollama-python drops
    the field when parsing the response (ollama/ollama-python#773), so the
    scenario-local mock returns a non-zero cached count and the capture
    transport reads it from the raw response, as an instrumentation with raw
    API access would. Once an SDK release exposes the field, the transport is
    removed and the value is read from the parsed response.

    The cached count is also recorded on the
    gen_ai.client.inference.usage.cache_read.input_tokens counter, a subset
    of the usage input-token counter, per the generic token metrics.
    """
    print("  [chat] cached prompt tokens (local /api/chat mock, raw-response capture)")
    mode = _capture_mode()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CachedPromptChatMockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_url = f"http://127.0.0.1:{port}"
        # The SDK forwards keyword arguments to its httpx client, so the
        # capture transport is injected through the supported transport
        # argument.
        transport = _CacheReadCaptureTransport(httpx.HTTPTransport())
        client = ollama.Client(host=base_url, transport=transport)
        request_model = "llama3.2"
        # The same request options as the other chats, so the span carries the
        # Ollama refinement attributes asserted once for all successful chats.
        request_options = {
            "seed": seed,
            "num_ctx": 2048,
            "num_batch": 512,
            "num_gpu": 1,
            "main_gpu": 0,
        }
        messages = [{"role": "user", "content": "Say hello."}]
        span_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": request_model,
            "gen_ai.request.seed": request_options["seed"],
            "ollama.request.base_url": _sanitize_base_url(base_url),
            "ollama.request.num_ctx": request_options["num_ctx"],
            "ollama.request.num_batch": request_options["num_batch"],
            "ollama.request.num_gpu": request_options["num_gpu"],
            "ollama.request.main_gpu": request_options["main_gpu"],
            "server.address": "127.0.0.1",
            "server.port": port,
        }
        # Message content is recorded on the span when the SPAN_ONLY or
        # SPAN_AND_EVENT capture mode is enabled, per the content capture
        # configuration section of docs/gen-ai/gen-ai-spans.md.
        if _record_span_messages(mode):
            span_attributes["gen_ai.input.messages"] = [
                {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
            ]
        input_tokens = None
        output_tokens = None
        response_model = None
        content = None
        with _reference_tracer.start_as_current_span(
            "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            started_at = perf_counter()
            resp = client.chat(model=request_model, messages=messages, stream=False, options=request_options)
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
            # The cached count is a subset of the prompt evaluation count, and
            # the SDK drops the field, so the value comes from the raw-response
            # capture and is only recorded when the server reports a non-zero
            # value, per the requirement level of the generic attribute.
            if transport.cached_prompt_tokens:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", transport.cached_prompt_tokens)
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
            metric_attributes["server.address"] = "127.0.0.1"
            metric_attributes["server.port"] = port
            _inference_duration.record(elapsed, metric_attributes)
            _operation_input_tokens.record(input_tokens if input_tokens is not None else 0, metric_attributes)
            _operation_output_tokens.record(output_tokens if output_tokens is not None else 0, metric_attributes)
            # Ollama reports no per-modality token breakdown, so every counter
            # point goes to the unknown modality, and the usage counters are
            # only incremented for known positive counts.
            if input_tokens:
                _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
            if output_tokens:
                _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})

            # The cached count is a subset of the input usage, so it is also
            # counted by the cache-read usage counter, next to the total.
            if transport.cached_prompt_tokens:
                _cache_read_input_tokens.add(
                    transport.cached_prompt_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"}
                )

            content = resp.message.content
            if _record_span_messages(mode):
                span.set_attribute(
                    "gen_ai.output.messages",
                    [{"role": "assistant", "parts": [{"type": "text", "content": content}]}],
                )
            event_attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "ollama",
                "gen_ai.request.model": request_model,
                "gen_ai.request.seed": request_options["seed"],
            }
            if _record_event_messages(mode):
                event_attrs["gen_ai.input.messages"] = [
                    {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages
                ]
                event_attrs["gen_ai.output.messages"] = [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": content}],
                    }
                ]
            if resp.model:
                event_attrs["gen_ai.response.model"] = resp.model
            event_attrs["gen_ai.response.finish_reasons"] = [resp.done_reason] if resp.done_reason else ["error"]
            if input_tokens is not None:
                event_attrs["gen_ai.usage.input_tokens"] = input_tokens
            if output_tokens is not None:
                event_attrs["gen_ai.usage.output_tokens"] = output_tokens
            if transport.cached_prompt_tokens:
                event_attrs["gen_ai.usage.cache_read.input_tokens"] = transport.cached_prompt_tokens
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


def run_chat_streaming_tools():
    """Scenario: streaming chat completion offering a tool.

    The request offers the weather tool through the SDK `tools` argument
    against a scenario-local /api/chat mock that answers with reasoning
    followed by a tool call, so the first chunk with output carries the
    reasoning payload and the stream also exercises the reasoning capture:
    the chunk arrival times, and with them time_to_first_chunk, are driven
    by the reasoning chunk, per the chunk definition.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingToolsMockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_url = f"http://127.0.0.1:{port}"
        client = ollama.Client(host=base_url)
        run_chat_streaming(client, base_url, tools=_WEATHER_TOOLS, seed=48, mock_host="127.0.0.1", mock_port=port)
    finally:
        server.shutdown()
        server.server_close()


def run_chat_streaming_failure():
    """Scenario: streaming chat completion that fails mid-stream.

    A scenario-local /api/chat mock serves the first chunk of the stream and
    then drops the connection, so the SDK raises a transport error after a
    chunk arrived: the failed span preserves gen_ai.response.time_to_first_chunk,
    the model and the partial output delivered before the failure, the
    finish reason falls back to "error", and the streaming chunk histograms
    are still recorded from the chunk that arrived, per their requirements.
    The run uses the SPAN_AND_EVENT capture mode, so the partial output is
    recorded on the span and, since the exception event may only copy
    attributes captured on the span, also carried by the exception event.
    The run fails if the call does not raise.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingFailureMockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_url = f"http://127.0.0.1:{port}"
        client = ollama.Client(host=base_url)
        try:
            run_chat_streaming(
                client,
                base_url,
                expect_error=True,
                seed=49,
                capture_mode="SPAN_AND_EVENT",
                mock_host="127.0.0.1",
                mock_port=port,
            )
        except _SDK_FAILURES as exc:
            print(f"    -> failed as expected ({type(exc).__name__})")
        else:
            raise RuntimeError("run_chat_streaming unexpectedly succeeded against the mid-stream failure mock")
    finally:
        server.shutdown()
        server.server_close()


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel(metric_views=_metric_views())
    # NO instrument() call - reference implementation only

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client, MOCK_BASE_URL)
    run_chat_with_tools(client, MOCK_BASE_URL)
    run_chat_formatted(client, MOCK_BASE_URL)
    run_chat_streaming(client, MOCK_BASE_URL)
    # The span content capture modes are exercised with explicit per-call
    # overrides: SPAN_ONLY records the messages on the span only, and
    # SPAN_AND_EVENT on both the span and the operation details event; the
    # mid-stream failure run below also uses SPAN_AND_EVENT, so its partial
    # output is captured on the span and copied to the exception event.
    run_chat(client, MOCK_BASE_URL, capture_mode="SPAN_ONLY", seed=46)
    run_chat(client, MOCK_BASE_URL, capture_mode="SPAN_AND_EVENT", seed=47)
    run_embed(client, MOCK_BASE_URL)
    run_text_completion()
    run_chat_cached_prompt()
    run_chat_streaming_tools()
    run_chat_streaming_failure()

    # The failure paths point the SDK at a server that accepts no
    # connections: error spans, exception events, and zero-valued metrics are
    # recorded and the SDK exception is re-raised.
    failing_client = ollama.Client(host=UNREACHABLE_BASE_URL)
    for operation in (run_chat, run_embed):
        _require_failure(operation, failing_client, UNREACHABLE_BASE_URL)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
