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


def run_chat():
    """Scenario: basic chat via Anthropic with reference implementation."""
    import anthropic

    print("  [chat] basic chat completion (reference implementation)")
    request_model = "claude-sonnet-4-20250514"
    request_max_tokens = 100
    messages = [{"role": "user", "content": "Say hello."}]
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
            json.dumps([{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]),
        )
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
            if cache_creation:
                span.set_attribute("gen_ai.usage.cache_creation.input_tokens", cache_creation)
            if cache_read:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", cache_read)
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

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [resp.stop_reason],
            "gen_ai.input.messages": json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
            ),
            "gen_ai.output.messages": output_messages,
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


def main():
    print("=== Reference Implementation: Anthropic Reference Implementation ===")

    tp, lp, mp = setup_otel()

    run_chat()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
