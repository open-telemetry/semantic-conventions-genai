"""Reference implementation for Anthropic using opentelemetry-util-genai.

`create_agent` uses a manual span instead: util-genai has no create-agent helper.
"""

import base64
import json
import os
from tempfile import mkdtemp
from time import perf_counter

import anthropic
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    Blob,
    FunctionToolDefinition,
    GenericToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
    ToolCallRequest,
)
from reference_shared import (
    ObservedStream,
    flush_and_shutdown,
    inference_duration_view,
    mock_server_host_port,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_meter = reference_meter()

_time_to_first_chunk = _reference_meter.create_histogram(
    "gen_ai.client.inference.time_to_first_chunk",
    unit="s",
    description="Time to receive the first output chunk of a streaming inference operation.",
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
_cache_read_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.cache_read.input_tokens",
    unit="{token}",
    description="The number of input tokens served from a provider-managed cache.",
)
_cache_write_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.cache_write.input_tokens",
    unit="{token}",
    description="The number of input tokens written to a provider-managed cache.",
)


def usage_metric_attributes(inv, request_model, server_address, server_port):
    """Build the attributes shared by every inference usage instrument.

    They mirror what util-genai puts on `gen_ai.client.operation.duration` for the
    same invocation.
    """
    attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": request_model,
    }
    if inv.response_model_name:
        attributes["gen_ai.response.model"] = inv.response_model_name
    if server_address:
        attributes["server.address"] = server_address
    if server_port is not None:
        attributes["server.port"] = server_port
    service_tier = inv.attributes.get("gen_ai.response.service_tier")
    if service_tier is not None:
        attributes["gen_ai.response.service_tier"] = service_tier
    return attributes


def record_inference_usage(inv, request_model, server_address, server_port, *, error=None):
    """Record the usage instruments from the same values the span carries.

    The Messages API reports no per-modality token breakdown - not even for the
    document and image scenarios - so every counter point goes to the `unknown`
    modality. Anthropic folds thinking tokens into `output_tokens` without a
    separate count, so there is no reasoning counter to record.
    """
    metric_attributes = usage_metric_attributes(inv, request_model, server_address, server_port)
    modality_attributes = {**metric_attributes, "gen_ai.token.modality": "unknown"}
    histogram_attributes = metric_attributes
    if error is not None:
        error_type = f"{type(error).__module__}.{type(error).__qualname__}"
        histogram_attributes = {**metric_attributes, "error.type": error_type}
    if inv.input_tokens is not None:
        _operation_input_tokens.record(inv.input_tokens, histogram_attributes)
        if inv.input_tokens > 0:
            _input_tokens.add(inv.input_tokens, modality_attributes)
    if inv.output_tokens is not None:
        _operation_output_tokens.record(inv.output_tokens, histogram_attributes)
        if inv.output_tokens > 0:
            _output_tokens.add(inv.output_tokens, modality_attributes)
    if inv.cache_read_input_tokens is not None and inv.cache_read_input_tokens > 0:
        _cache_read_input_tokens.add(inv.cache_read_input_tokens, modality_attributes)
    cache_write = inv.attributes.get("gen_ai.usage.cache_write.input_tokens")
    if cache_write is not None and cache_write > 0:
        _cache_write_input_tokens.add(cache_write, modality_attributes)


def run_chat(handler):
    """Scenario: basic chat completion with reasoning.level."""
    print("  [chat] basic chat completion (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    request_reasoning_level = "medium"
    request_service_tier = "auto"
    system_instruction = "Answer briefly."
    messages = [{"role": "user", "content": "Say hello."}]
    tool = {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    }
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens
        inv.attributes["gen_ai.request.reasoning.level"] = request_reasoning_level  # -> gen_ai.request.reasoning.level
        inv.attributes["gen_ai.request.service_tier"] = request_service_tier  # -> gen_ai.request.service_tier
        inv.system_instruction = [Text(content=system_instruction)]  # -> gen_ai.system_instructions
        inv.tool_definitions = [  # -> gen_ai.tool.definitions
            FunctionToolDefinition(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["input_schema"],
            )
        ]
        (user_message,) = messages
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(role=user_message["role"], parts=[Text(content=user_message["content"])])
        ]

        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            output_config={"effort": request_reasoning_level},
            service_tier=request_service_tier,
            system=system_instruction,
            tools=[tool],
        )

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            service_tier = resp.usage.service_tier
            if service_tier is not None:
                inv.attributes["gen_ai.response.service_tier"] = service_tier  # -> gen_ai.response.service_tier
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            inv.input_tokens = resp.usage.input_tokens + cache_creation + cache_read  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens
            if cache_creation:
                inv.attributes["gen_ai.usage.cache_write.input_tokens"] = (
                    cache_creation  # -> gen_ai.usage.cache_write.input_tokens
                )
            if cache_read:
                inv.cache_read_input_tokens = cache_read  # -> gen_ai.usage.cache_read.input_tokens

        output_parts = []
        for block in resp.content:
            if hasattr(block, "text"):
                output_parts.append(Text(content=block.text))
            elif block.type == "tool_use":
                output_parts.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )
        if output_parts:
            inv.output_messages = [  # -> gen_ai.output.messages
                OutputMessage(role="assistant", parts=output_parts)
            ]
        record_inference_usage(inv, request_model, host, port)

    first_block = resp.content[0]
    if hasattr(first_block, "text"):
        print(f"    -> {first_block.text[:60]}")
    elif first_block.type == "tool_use":
        print(f"    -> tool_call: {first_block.name}")
    else:
        print(f"    -> {first_block.type}")


def run_chat_streaming_close(handler, client, *, close_early=True):
    """Scenario: leave the Messages stream context after its first text delta."""
    print("  [chat_streaming_close] caller closes before the final message")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    messages = [{"role": "user", "content": "Tell me a story."}]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.attributes["gen_ai.request.stream"] = True
        inv.max_tokens = request_max_tokens
        inv.input_messages = [InputMessage(role="user", parts=[Text(content=messages[0]["content"])])]
        text = ""
        started_at = perf_counter()
        stream = ObservedStream(
            client.messages.stream(model=request_model, max_tokens=request_max_tokens, messages=messages)
        )
        try:
            with stream:
                for event in stream:
                    received_at = perf_counter()
                    if event.type == "message_start":
                        message = event.message
                        inv.response_id = message.id
                        inv.response_model_name = message.model
                        cache_read = message.usage.cache_read_input_tokens or 0
                        cache_write = message.usage.cache_creation_input_tokens or 0
                        inv.input_tokens = message.usage.input_tokens + cache_read + cache_write
                        inv.cache_read_input_tokens = cache_read or None
                        if cache_write:
                            inv.attributes["gen_ai.usage.cache_write.input_tokens"] = cache_write
                        inv.output_tokens = message.usage.output_tokens
                    elif event.type == "message_delta":
                        if event.delta.stop_reason:
                            inv.finish_reasons = [event.delta.stop_reason]
                        inv.output_tokens = event.usage.output_tokens
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta" and event.delta.text:
                        if not text:
                            ttfc = received_at - started_at
                            inv.attributes["gen_ai.response.time_to_first_chunk"] = ttfc
                            _time_to_first_chunk.record(ttfc, usage_metric_attributes(inv, request_model, host, port))
                        text += event.delta.text
                        if close_early:
                            break
        finally:
            if not inv.finish_reasons:
                inv.finish_reasons = [stream.finish_reason]
            if text:
                inv.output_messages = [OutputMessage(role="assistant", parts=[Text(content=text)])]
            record_inference_usage(inv, request_model, host, port, error=stream.error)
            print(f"    -> {inv.finish_reasons[0]}, input tokens: {inv.input_tokens}")


def run_chat_streaming_checks():
    """Check stream endings and first-chunk timing through the SDK."""
    from unittest.mock import patch

    import httpx2
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.util.genai.handler import TelemetryHandler

    def check_stream(*, close_early=False, stop_reason=None, stream_error=False, include_text=True):
        observed = []
        responses = []
        now = 0.0
        stream_type = ObservedStream

        def observe(manager):
            stream = stream_type(manager)
            observed.append(stream)
            return stream

        def events():
            nonlocal now
            payloads = [
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg-stream",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-4-20250514",
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 10, "output_tokens": 1, "cache_read_input_tokens": 2},
                    },
                },
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": ""}},
            ]
            if include_text:
                payloads.extend(
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}
                    for text in ("Hello", " world")
                )
            payloads.extend(
                (
                    {"type": "content_block_stop", "index": 0},
                    {"type": "message_delta", "delta": {"stop_reason": stop_reason}, "usage": {"output_tokens": 3}},
                )
            )
            if stream_error:
                payloads.append({"type": "error", "error": {"type": "overloaded_error", "message": "stream failed"}})
            else:
                payloads.append({"type": "message_stop"})
            for payload in payloads:
                now += 0.125
                yield f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n".encode()

        def respond(request):
            nonlocal now
            assert request.url.path == "/v1/messages"
            request_body = json.loads(request.content)
            assert request_body["stream"] is True
            assert request_body["max_tokens"] == 100
            now += 0.5
            response = httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=events())
            responses.append(response)
            return response

        exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        meter_provider = MeterProvider()
        logger_provider = LoggerProvider()
        try:
            handler = TelemetryHandler(
                tracer_provider=tracer_provider, meter_provider=meter_provider, logger_provider=logger_provider
            )
            with (
                patch(f"{__name__}.ObservedStream", side_effect=observe),
                patch(f"{__name__}.perf_counter", side_effect=lambda: now),
                patch(f"{__name__}._time_to_first_chunk") as histogram,
                patch(f"{__name__}._operation_input_tokens") as input_histogram,
                patch(f"{__name__}._operation_output_tokens") as output_histogram,
                patch(f"{__name__}._input_tokens") as input_counter,
                patch(f"{__name__}._output_tokens") as output_counter,
                anthropic.Anthropic(
                    api_key="mock-key",
                    base_url=MOCK_BASE_URL,
                    max_retries=0,
                    http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
                ) as client,
            ):
                try:
                    run_chat_streaming_close(handler, client, close_early=close_early)
                except anthropic.APIError:
                    if not stream_error:
                        raise
                else:
                    assert not stream_error, "expected the Anthropic SDK to raise"

            (span,) = exporter.get_finished_spans()
            (stream,) = observed
            (http_response,) = responses
            assert stream.closed_early == (close_early or stream_error)
            assert stream.exhausted == (not (close_early or stream_error))
            assert http_response.is_closed
            expected_reason = "interrupted" if close_early else stop_reason or "error"
            assert span.attributes["gen_ai.response.finish_reasons"] == (expected_reason,)
            assert span.attributes["gen_ai.request.max_tokens"] == 100
            if include_text:
                assert span.attributes["gen_ai.response.time_to_first_chunk"] == 1.0
                host, port = mock_server_host_port(MOCK_BASE_URL)
                histogram.record.assert_called_once_with(
                    1.0,
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.provider.name": "anthropic",
                        "gen_ai.request.model": "claude-sonnet-4-20250514",
                        "gen_ai.response.model": "claude-sonnet-4-20250514",
                        "server.address": host,
                        "server.port": port,
                    },
                )
            else:
                assert "gen_ai.response.time_to_first_chunk" not in span.attributes
                histogram.record.assert_not_called()
            assert span.attributes["gen_ai.usage.input_tokens"] == 12
            assert span.attributes["gen_ai.usage.output_tokens"] == (1 if close_early else 3)
            assert span.status.status_code == (StatusCode.ERROR if stream_error else StatusCode.UNSET)
            assert ("error.type" in span.attributes) == stream_error
            host, port = mock_server_host_port(MOCK_BASE_URL)
            attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": "claude-sonnet-4-20250514",
                "gen_ai.response.model": "claude-sonnet-4-20250514",
                "server.address": host,
                "server.port": port,
            }
            histogram_attributes = dict(attributes)
            if stream_error:
                histogram_attributes["error.type"] = span.attributes["error.type"]
            counter_attributes = {**attributes, "gen_ai.token.modality": "unknown"}
            input_histogram.record.assert_called_once_with(12, histogram_attributes)
            output_histogram.record.assert_called_once_with(1 if close_early else 3, histogram_attributes)
            input_counter.add.assert_called_once_with(12, counter_attributes)
            output_counter.add.assert_called_once_with(1 if close_early else 3, counter_attributes)
        finally:
            tracer_provider.shutdown()
            meter_provider.shutdown()
            logger_provider.shutdown()

    check_stream()
    check_stream(close_early=True)
    check_stream(stop_reason="end_turn")
    check_stream(stream_error=True)
    check_stream(stop_reason="end_turn", stream_error=True)
    check_stream(stop_reason="end_turn", include_text=False)
    print("    -> chat streaming checks passed")


def _has_compaction_block_in_input(messages):
    """Return True if any input message contains a compaction content block."""
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if block_type == "compaction":
                    return True
    return False


def _has_compaction_block_in_response(response):
    """Return True if the response carries a compaction signal."""
    if getattr(response, "stop_reason", None) == "compaction":
        return True
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "compaction":
            return True
    return any(
        getattr(it, "type", None) == "compaction"
        for it in getattr(getattr(response, "usage", None), "iterations", []) or []
    )


def run_compaction(handler):
    """Scenario: server-side compaction via context_management beta.

    gen_ai.conversation.compacted is set via inv.attributes since
    InferenceInvocation does not have a first-class property for it yet.
    Compaction blocks have no util-genai part type (`GenericPart` would serialize
    as `{"type": "generic", ...}`, not the semconv shape), so they are emitted as
    plain dict parts inside `InputMessage`/`OutputMessage`; `dataclasses.asdict`
    recurses into them, so the span and the event carry the same shape. The
    compaction parts stay type-only (no `content`): Anthropic only exposes an
    encrypted, opaque compaction state here, never the unencrypted summary
    CompactionPart.content documents, so it would be dishonest to fabricate one.
    """
    print("  [chat_compaction] chat with server-side compaction (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "compaction",
                    "encrypted_content": "opaque encrypted compaction state from a prior turn",
                }
            ],
        },
        {"role": "user", "content": "Continue this long conversation."},
    ]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens

        # Compaction blocks have no util-genai part type, but `dataclasses.asdict`
        # recurses into plain dicts, so a dict part reaches the span and the event
        # in the same semconv shape.
        compaction_message, user_message = messages
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(role=compaction_message["role"], parts=[{"type": "compaction"}]),
            InputMessage(role=user_message["role"], parts=[Text(content=user_message["content"])]),
        ]

        resp = client.beta.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            context_management={
                "edits": [
                    {
                        "type": "compact_20260112",
                        "trigger": {"type": "input_tokens", "value": 200000},
                        "pause_after_compaction": True,
                    }
                ]
            },
            betas=["context-management-2026-01-12"],
        )

        conversation_compacted = _has_compaction_block_in_input(messages) or _has_compaction_block_in_response(resp)
        inv.attributes["gen_ai.conversation.compacted"] = conversation_compacted  # -> gen_ai.conversation.compacted

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            inv.input_tokens = resp.usage.input_tokens  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens

        output_parts = []
        for block in getattr(resp, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text" and getattr(block, "text", None):
                output_parts.append({"type": "text", "content": block.text})
            elif block_type == "compaction":
                # Anthropic only ever returns `encrypted_content` here, never the
                # unencrypted summary CompactionPart.content documents, so this part
                # stays type-only.
                output_parts.append({"type": "compaction"})
        if output_parts:
            inv.output_messages = [  # -> gen_ai.output.messages
                OutputMessage(role="assistant", parts=output_parts),
            ]
        record_inference_usage(inv, request_model, host, port)

    print(f"    -> compacted: {conversation_compacted}")


def run_chat_with_document_input(handler):
    """Scenario: chat with a PDF document block (document modality)."""
    print("  [chat_document] chat with PDF document block (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    instruction = "Summarize the attached document in one sentence."
    pdf_bytes = b"%PDF-1.4\n%mock pdf for reference scenario\n%%EOF\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    mime_type = "application/pdf"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": pdf_b64,
                    },
                },
            ],
        }
    ]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(
                role="user",
                parts=[
                    Text(content=instruction),
                    Blob(mime_type=mime_type, modality="document", content=pdf_bytes),
                ],
            )
        ]

        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
        )

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            inv.input_tokens = resp.usage.input_tokens + cache_creation + cache_read  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens
            if cache_creation:
                inv.attributes["gen_ai.usage.cache_write.input_tokens"] = (
                    cache_creation  # -> gen_ai.usage.cache_write.input_tokens
                )
            if cache_read:
                inv.cache_read_input_tokens = cache_read  # -> gen_ai.usage.cache_read.input_tokens

        inv.output_messages = [  # -> gen_ai.output.messages
            OutputMessage(
                role="assistant",
                parts=[Text(content=block.text)],
            )
            for block in resp.content
            if hasattr(block, "text")
        ]
        record_inference_usage(inv, request_model, host, port)

    print(f"    -> {resp.content[0].text[:60]}")


def run_chat_with_named_documents(handler):
    """Scenario: chat with titled document blocks from base64, file and URL sources.

    Each document block's `title` is recorded as `name` on the matching part:
    base64 source -> `blob`, `file` source -> `file`, `url` source -> `uri`.
    util-genai's `Blob` has no `name` yet, so the parts are passed as plain dicts.
    """
    print("  [chat_named_documents] chat with titled document blocks (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    instruction = "Compare the three attached contracts."
    pdf_bytes = b"%PDF-1.4\n%mock pdf for reference scenario\n%%EOF\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    mime_type = "application/pdf"
    inline_doc = {
        "type": "document",
        "source": {"type": "base64", "media_type": mime_type, "data": pdf_b64},
        "title": "Contract 2024",
    }
    file_doc = {
        "type": "document",
        "source": {"type": "file", "file_id": "file_011CNha8iCJcU1wXNR6q4V8w"},
        "title": "Contract 2025",
    }
    url_doc = {
        "type": "document",
        "source": {"type": "url", "url": "https://example.com/contracts/2026.pdf"},
        "title": "Contract 2026",
    }
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": instruction}, inline_doc, file_doc, url_doc],
        }
    ]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(
                role="user",
                parts=[
                    Text(content=instruction),
                    {
                        "type": "blob",
                        "modality": "document",
                        "mime_type": inline_doc["source"]["media_type"],
                        "content": pdf_bytes,
                        "name": inline_doc["title"],
                    },
                    {
                        "type": "file",
                        "modality": "document",
                        "file_id": file_doc["source"]["file_id"],
                        "name": file_doc["title"],
                    },
                    {
                        "type": "uri",
                        "modality": "document",
                        "uri": url_doc["source"]["url"],
                        "name": url_doc["title"],
                    },
                ],
            )
        ]

        resp = client.beta.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            betas=["files-api-2025-04-14"],
        )

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            inv.input_tokens = resp.usage.input_tokens  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens

        output_parts = [Text(content=block.text) for block in resp.content if hasattr(block, "text")]
        if output_parts:
            inv.output_messages = [  # -> gen_ai.output.messages
                OutputMessage(role="assistant", parts=output_parts)
            ]
        record_inference_usage(inv, request_model, host, port)

    print(f"    -> {resp.content[0].text[:60]}")


def run_chat_with_image_input(handler):
    """Scenario: chat with an image block (image modality)."""
    print("  [chat_image] chat with image block (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    instruction = "Describe the attached image."
    image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    mime_type = "image/png"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_b64,
                    },
                },
            ],
        }
    ]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(
                role="user",
                parts=[
                    Text(content=instruction),
                    Blob(mime_type=mime_type, modality="image", content=image_bytes),
                ],
            )
        ]

        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
        )

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            inv.input_tokens = resp.usage.input_tokens + cache_creation + cache_read  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens
            if cache_creation:
                inv.attributes["gen_ai.usage.cache_write.input_tokens"] = (
                    cache_creation  # -> gen_ai.usage.cache_write.input_tokens
                )
            if cache_read:
                inv.cache_read_input_tokens = cache_read  # -> gen_ai.usage.cache_read.input_tokens

        inv.output_messages = [  # -> gen_ai.output.messages
            OutputMessage(
                role="assistant",
                parts=[Text(content=block.text)],
            )
            for block in resp.content
            if hasattr(block, "text")
        ]
        record_inference_usage(inv, request_model, host, port)

    print(f"    -> {resp.content[0].text[:60]}")


def run_chat_with_search_result_input(handler):
    """Scenario: chat with a search result block and a built-in web search tool.

    Search result blocks and built-in tools have no defined semconv type, so
    both are recorded with `type` prefixed by `gen_ai.provider.name` (`anthropic.`).
    """
    print("  [chat_search_result] chat with search result block (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    instruction = "Answer using the attached search result."
    search_result = {
        "type": "search_result",
        "source": "https://example.com/docs/otel",
        "title": "OpenTelemetry overview",
        "content": [{"type": "text", "text": "OpenTelemetry is an observability framework."}],
        "citations": {"enabled": True},
    }
    tools = [{"type": "web_search_20250305", "name": "web_search"}]
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": instruction}, search_result],
        }
    ]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    with handler.inference(
        provider="anthropic",
        request_model=request_model,
        server_address=host,
        server_port=port,
    ) as inv:
        inv.max_tokens = request_max_tokens  # -> gen_ai.request.max_tokens
        # util-genai has no type for provider-specific parts, so pass a plain dict.
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(
                role="user",
                parts=[
                    Text(content=instruction),
                    {**search_result, "type": f"anthropic.{search_result['type']}"},
                ],
            )
        ]
        inv.tool_definitions = [  # -> gen_ai.tool.definitions
            GenericToolDefinition(name=t["name"], type=f"anthropic.{t['type']}") for t in tools
        ]

        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            tools=tools,
        )

        inv.response_model_name = resp.model  # -> gen_ai.response.model
        inv.response_id = resp.id  # -> gen_ai.response.id
        inv.finish_reasons = [resp.stop_reason]  # -> gen_ai.response.finish_reasons

        if resp.usage:
            inv.input_tokens = resp.usage.input_tokens  # -> gen_ai.usage.input_tokens
            inv.output_tokens = resp.usage.output_tokens  # -> gen_ai.usage.output_tokens

        output_parts = [Text(content=block.text) for block in resp.content if hasattr(block, "text")]
        if output_parts:
            inv.output_messages = [  # -> gen_ai.output.messages
                OutputMessage(role="assistant", parts=output_parts)
            ]
        record_inference_usage(inv, request_model, host, port)

    print(f"    -> {resp.content[0].type}")


def run_create_agent():
    """Scenario: create a remote agent via the Managed Agents API (`beta.agents.create`).

    The agent runs server-side, so only the client operation is instrumentable here.
    """
    print("  [create_agent] Anthropic Managed Agents: create agent")
    request_model = "claude-sonnet-5"
    agent_name = "reference-agent"
    agent_description = "Reference managed agent."
    agent_system = "You are a helpful assistant. Answer the user's questions accurately and concisely."
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent_name,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with reference_tracer().start_as_current_span(
        f"create_agent {agent_name}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.agent.description", agent_description)
        span.set_attribute("gen_ai.system_instructions", [{"type": "text", "content": agent_system}])
        try:
            agent = client.beta.agents.create(
                model=request_model,
                name=agent_name,
                description=agent_description,
                system=agent_system,
            )
            span.set_attribute("gen_ai.agent.id", agent.id)
            span.set_attribute("gen_ai.agent.version", str(agent.version))
            print(f"    -> {agent.id}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def main(*, caller_close=False):
    """Run all Anthropic reference scenarios."""
    print("=== Reference Implementation: Anthropic (util-genai) ===")

    # Keep controlled-clock checks separate from the OTLP-exported reference run.
    run_chat_streaming_checks()

    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "SPAN_AND_EVENT"
    os.environ["OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT"] = "true"

    tp, lp, mp = setup_otel(metric_views=(inference_duration_view(),))
    os.environ["OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK"] = "upload"
    os.environ["OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH"] = mkdtemp()
    handler = get_telemetry_handler(
        tracer_provider=tp,
        meter_provider=mp,
        logger_provider=lp,
        completion_hook=load_completion_hook(),
    )

    if caller_close:
        with anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key") as client:
            run_chat_streaming_close(handler, client)
        flush_and_shutdown(tp, lp, mp)
        return

    run_chat(handler)
    run_compaction(handler)
    run_chat_with_document_input(handler)
    run_chat_with_named_documents(handler)
    run_chat_with_image_input(handler)
    run_chat_with_search_result_input(handler)
    run_create_agent()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
