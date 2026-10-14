"""Reference implementation for Azure OpenAI."""

import os
import time

from opentelemetry.trace import StatusCode
from reference_shared import flush_and_shutdown, mock_server_host_port, reference_meter, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_embeddings_duration = _reference_meter.create_histogram(
    "gen_ai.client.embeddings.duration",
    unit="s",
    description="GenAI client embeddings operation duration.",
    explicit_bucket_boundaries_advisory=[
        0.01,
        0.02,
        0.04,
        0.08,
        0.16,
        0.32,
        0.64,
        1.28,
        2.56,
        5.12,
        10.24,
        20.48,
        40.96,
        81.92,
    ],
)
_embeddings_input_tokens = _reference_meter.create_histogram(
    "gen_ai.client.embeddings.operation.input_tokens",
    unit="{token}",
    description="The number of input tokens used per embeddings operation.",
    explicit_bucket_boundaries_advisory=[
        1,
        4,
        16,
        64,
        256,
        1024,
        4096,
        16384,
        65536,
        262144,
        1048576,
        4194304,
        16777216,
        67108864,
    ],
)


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "gpt-4o-mini"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        messages = [{"role": "user", "content": "Say hello."}]
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_embeddings_reference(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "text-embedding-3-small"
    request_encoding_format = "float"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    start_time = time.perf_counter()
    metric_attributes = dict(span_attributes_2)
    with _reference_tracer.start_as_current_span(
        "embeddings text-embedding-3-small", attributes=span_attributes_2
    ) as span:
        try:
            span.set_attribute("gen_ai.request.encoding_formats", [request_encoding_format])
            resp = client.embeddings.create(
                model=request_model,
                input="Hello, world!",
                encoding_format=request_encoding_format,
            )
            span.set_attribute("gen_ai.response.model", resp.model)
            if resp.data and resp.data[0].embedding is not None:
                span.set_attribute("gen_ai.embeddings.dimension.count", len(resp.data[0].embedding))
            if resp.usage:
                span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            metric_attributes["gen_ai.response.model"] = resp.model
            if resp.usage:
                _embeddings_input_tokens.record(resp.usage.prompt_tokens, metric_attributes)
            print(f"    -> embedding dim: {len(resp.data[0].embedding)}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes["error.type"] = type(e).__qualname__
            raise
        finally:
            _embeddings_duration.record(time.perf_counter() - start_time, metric_attributes)


def main():
    print("=== Reference Implementation: Azure OpenAI Reference ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.AzureOpenAI(
        azure_endpoint=MOCK_BASE_URL,
        api_key="mock-key",
        api_version="2024-06-01",
    )

    run_chat_reference(client)
    run_embeddings_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
