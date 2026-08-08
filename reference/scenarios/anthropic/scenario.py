"""Reference implementation for Anthropic using opentelemetry-util-genai.

`create_agent` uses a manual span instead: util-genai has no create-agent helper.
"""

import base64
import json
import os

import anthropic
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import Blob, InputMessage, OutputMessage, Text
from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]


def run_chat(handler):
    """Scenario: basic chat completion with reasoning.level."""
    print("  [chat] basic chat completion (util-genai handler)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    request_reasoning_level = "medium"
    messages = [{"role": "user", "content": "Say hello."}]
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
        (user_message,) = messages
        inv.input_messages = [  # -> gen_ai.input.messages
            InputMessage(role=user_message["role"], parts=[Text(content=user_message["content"])])
        ]

        resp = client.messages.create(
            model=request_model,
            max_tokens=request_max_tokens,
            messages=messages,
            output_config={"effort": request_reasoning_level},
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

        output_parts = [Text(content=block.text) for block in resp.content if hasattr(block, "text")]
        if output_parts:
            inv.output_messages = [  # -> gen_ai.output.messages
                OutputMessage(role="assistant", parts=output_parts, finish_reason=resp.stop_reason)
            ]

    print(f"    -> {resp.content[0].text[:60]}")


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
                OutputMessage(role="assistant", parts=output_parts, finish_reason=resp.stop_reason),
            ]

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
                finish_reason=resp.stop_reason,
            )
            for block in resp.content
            if hasattr(block, "text")
        ]

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
                finish_reason=resp.stop_reason,
            )
            for block in resp.content
            if hasattr(block, "text")
        ]

    print(f"    -> {resp.content[0].text[:60]}")


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
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": agent_system}]))
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


def main():
    """Run all Anthropic reference scenarios."""
    print("=== Reference Implementation: Anthropic (util-genai) ===")

    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "SPAN_AND_EVENT"
    os.environ["OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT"] = "true"

    tp, lp, mp = setup_otel()
    handler = get_telemetry_handler(
        tracer_provider=tp,
        meter_provider=mp,
        logger_provider=lp,
    )

    run_chat(handler)
    run_compaction(handler)
    run_chat_with_document_input(handler)
    run_chat_with_image_input(handler)
    run_create_agent()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
