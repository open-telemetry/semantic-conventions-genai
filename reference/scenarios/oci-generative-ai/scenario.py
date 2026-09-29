"""Reference implementation for OCI Generative AI (OpenAI-compatible endpoint)."""

import os

from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

# OCI Generative AI serves the OpenAI API at
# https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1.
# Instrumentation recognises the provider from that base_url host suffix
# (`.oci.oraclecloud.com`); the mock server stands in for the host here.
OCI_PROVIDER_NAME = "oracle_cloud.generative_ai"

_reference_tracer = reference_tracer()


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "meta.llama-3.3-70b-instruct"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": OCI_PROVIDER_NAME,
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(f"chat {request_model}", attributes=span_attributes) as span:
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


def main():
    print("=== Reference Implementation: OCI Generative AI (OpenAI-compatible) ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(
        base_url=f"{MOCK_BASE_URL}/openai/v1",
        api_key="mock-key",
    )

    run_chat_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
