"""Reference implementation for Anthropic.

Exercises: chat completion
against a mock Anthropic server, with manual OTel spans.
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


def response_has_compaction_block(response):
    """Return whether Anthropic reported compaction in response content or usage."""
    if getattr(response, "stop_reason", None) == "compaction":
        return True
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "compaction":
            return True
    usage = getattr(response, "usage", None)
    return any(getattr(iteration, "type", None) == "compaction" for iteration in getattr(usage, "iterations", []) or [])


def input_has_compaction_block(messages):
    """Return whether Anthropic input messages include a compaction block."""
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if block_type == "compaction":
                    return True
    return False


def input_messages(messages):
    """Convert Anthropic input messages into OTel input messages."""
    converted_messages = []
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        parts = []
        if isinstance(content, str):
            parts.append({"type": "text", "content": content})
        elif isinstance(content, list):
            for block in content:
                block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if block_type == "text":
                    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                    if text:
                        parts.append({"type": "text", "content": text})
                elif block_type == "compaction":
                    compaction_content = (
                        block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
                    )
                    compaction_part = {"type": "compaction"}
                    if compaction_content:
                        compaction_part["content"] = compaction_content
                    parts.append(compaction_part)
        if parts:
            converted_messages.append({"role": role or "user", "parts": parts})
    return converted_messages


def response_output_messages(response):
    """Convert Anthropic response content blocks into OTel output messages."""
    parts = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text" and getattr(block, "text", None):
            parts.append({"type": "text", "content": block.text})
        elif block_type == "compaction":
            compaction_part = {"type": "compaction"}
            compaction_content = getattr(block, "content", None)
            if compaction_content:
                compaction_part["content"] = compaction_content
            parts.append(compaction_part)
    if not parts:
        return []
    return [
        {
            "role": "assistant",
            "parts": parts,
            "finish_reason": getattr(response, "stop_reason", None) or "stop",
        }
    ]


def run_chat():
    """Scenario: basic chat via Anthropic with reference implementation."""
    import anthropic

    print("  [chat] basic chat completion (reference implementation)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    request_reasoning_level = "medium"
    messages = [{"role": "user", "content": "Say hello."}]
    input_messages_json = json.dumps(input_messages(messages))
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat claude-sonnet-4-20250514", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.request.reasoning.level", request_reasoning_level)
        span.set_attribute(
            "gen_ai.input.messages",
            input_messages_json,
        )
        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            output_config={"effort": request_reasoning_level},
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [resp.stop_reason])
        output_messages = response_output_messages(resp)
        if resp.usage:
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            total_input = resp.usage.input_tokens + cache_creation + cache_read
            span.set_attribute("gen_ai.usage.input_tokens", total_input)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
            if cache_creation:
                span.set_attribute("gen_ai.usage.cache_creation.input_tokens", cache_creation)
            if cache_read:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", cache_read)
        output_messages_json = json.dumps(output_messages)
        span.set_attribute("gen_ai.output.messages", output_messages_json)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [resp.stop_reason],
            "gen_ai.input.messages": input_messages_json,
            "gen_ai.output.messages": output_messages_json,
        }
        if resp.usage:
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            total_input = resp.usage.input_tokens + cache_creation + cache_read
            event_attrs["gen_ai.usage.input_tokens"] = total_input
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.output_tokens
            if cache_creation:
                event_attrs["gen_ai.usage.cache_creation.input_tokens"] = cache_creation
            if cache_read:
                event_attrs["gen_ai.usage.cache_read.input_tokens"] = cache_read
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.content[0].text[:60]}")


def run_compaction_reference():
    """Scenario: Anthropic server-side compaction signal from compaction blocks."""
    import anthropic

    print("  [chat_compaction] chat with server-side compaction (reference implementation)")
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
    input_messages_json = json.dumps(input_messages(messages))
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat claude-sonnet-4-20250514", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute(
            "gen_ai.input.messages",
            input_messages_json,
        )
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

        # Provider-side instrumentation derives this from live SDK-visible
        # state: either a compaction block in the input conversation carried
        # forward from a prior turn, or a response compaction signal.
        conversation_compacted = input_has_compaction_block(messages) or response_has_compaction_block(resp)
        span.set_attribute("gen_ai.conversation.compacted", conversation_compacted)
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [resp.stop_reason])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
        output_messages = response_output_messages(resp)
        if output_messages:
            span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))

        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.conversation.compacted": conversation_compacted,
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [resp.stop_reason],
            "gen_ai.input.messages": input_messages_json,
        }
        if output_messages:
            event_attrs["gen_ai.output.messages"] = json.dumps(output_messages)
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )
        print(f"    -> compacted: {conversation_compacted}")


def run_chat_with_document_input():
    """Scenario: chat with a base64 document block (document modality).

    Exercises the `document` value of the `Modality` enum on a `BlobPart`
    in `gen_ai.input.messages`. Anthropic's Messages API has a first-class
    `document` content block that exposes the mime type and source bytes
    directly on the SDK call boundary -- so every emitted BlobPart field
    traces back to the SDK arg without any Files-API roundtrip:

      {"type": "document",
       "source": {"type": "base64", "media_type": "application/pdf", "data": "..."}}
    """
    import base64

    import anthropic

    print("  [chat_document] chat with PDF document block (reference implementation)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    instruction = "Summarize the attached document in one sentence."
    pdf_bytes = b"%PDF-1.4\n%mock pdf for reference scenario\n%%EOF\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    mime_type = "application/pdf"

    # SDK boundary: native Anthropic document content block.
    user_content = [
        {"type": "text", "text": instruction},
        {
            "type": "document",
            "source": {"type": "base64", "media_type": mime_type, "data": pdf_b64},
        },
    ]
    messages = [{"role": "user", "content": user_content}]
    client = anthropic.Anthropic(base_url=MOCK_BASE_URL, api_key="mock-key")

    # Canonical OTel parts: TextPart + BlobPart(modality="document"). Each
    # BlobPart field is derivable from the document block above:
    #   - mime_type: `source.media_type`
    #   - content:   `source.data` (already base64)
    #   - modality:  classification of media_type "application/pdf"
    input_parts = [
        {"type": "text", "content": instruction},
        {
            "type": "blob",
            "modality": "document",
            "mime_type": mime_type,
            "content": pdf_b64,
        },
    ]
    input_messages = json.dumps([{"role": "user", "parts": input_parts}])

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_doc = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_doc["server.address"] = host
    if port is not None:
        span_attributes_doc["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "chat claude-sonnet-4-20250514", attributes=span_attributes_doc
    ) as span:
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [resp.stop_reason])
        if resp.usage:
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", None) or 0
            cache_read = getattr(resp.usage, "cache_read_input_tokens", None) or 0
            total_input = resp.usage.input_tokens + cache_creation + cache_read
            span.set_attribute("gen_ai.usage.input_tokens", total_input)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
        output_messages = json.dumps(
            [
                {
                    "role": "assistant",
                    "parts": [{"type": "text", "content": block.text}],
                    "finish_reason": resp.stop_reason,
                }
                for block in resp.content
                if hasattr(block, "text")
            ]
        )
        span.set_attribute("gen_ai.output.messages", output_messages)
        print(f"    -> {resp.content[0].text[:60]}")


def main():
    print("=== Reference Implementation: Anthropic Reference Implementation ===")

    tp, lp, mp = setup_otel()

    run_chat()
    run_compaction_reference()
    run_chat_with_document_input()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
