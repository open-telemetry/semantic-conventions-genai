"""Reference implementation for Ollama.

Exercises: chat
against a mock Ollama server, with manual OTel spans.
"""

import os

from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()


def run_chat(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "llama3.2"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request_model,
        "gen_ai.request.max_tokens": 100,
        "gen_ai.request.temperature": 0.5,
        "gen_ai.request.top_p": 0.9,
        "gen_ai.request.top_k": 40,
        "gen_ai.request.stop_sequences": ["\n\n"],
        "gen_ai.request.seed": 42,
        "ollama.request.base_url": MOCK_BASE_URL,
        "ollama.request.num_ctx": 2048,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    with _reference_tracer.start_as_current_span(
        "chat llama3.2", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        resp = client.chat(
            model=request_model,
            messages=messages,
            stream=False,
            options={
                "num_predict": 100,
                "temperature": 0.5,
                "top_p": 0.9,
                "top_k": 40,
                "stop": ["\n\n"],
                "seed": 42,
                "num_ctx": 2048,
            },
        )
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.done_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [resp.done_reason])
        if resp.prompt_eval_count is not None:
            span.set_attribute("gen_ai.usage.input_tokens", int(resp.prompt_eval_count))
        if resp.eval_count is not None:
            span.set_attribute("gen_ai.usage.output_tokens", int(resp.eval_count))
        if resp.total_duration is not None:
            span.set_attribute("ollama.response.total_duration", int(resp.total_duration))
        if resp.load_duration is not None:
            span.set_attribute("ollama.response.load_duration", int(resp.load_duration))

        content = resp.message.content
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": request_model,
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
        if resp.prompt_eval_count is not None:
            event_attrs["gen_ai.usage.input_tokens"] = int(resp.prompt_eval_count)
        if resp.eval_count is not None:
            event_attrs["gen_ai.usage.output_tokens"] = int(resp.eval_count)
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {content[:60]}")


def main():
    print("=== Reference Implementation: Ollama ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    import ollama

    client = ollama.Client(host=MOCK_BASE_URL)

    run_chat(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
