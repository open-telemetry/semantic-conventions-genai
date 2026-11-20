"""Reference implementation for OCI Generative AI (OpenAI-compatible endpoint)."""

import os

import httpx2
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_meter, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

# OCI Generative AI serves the OpenAI API at
# https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1.
# The client is configured with that real base_url; a transport hands the
# requests to the mock server, so the client's own state stays representative.
OCI_BASE_URL = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/openai/v1"
OCI_HOST_SUFFIX = ".oci.oraclecloud.com"
OCI_PROVIDER_NAME = "oracle_cloud.generative_ai"

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_TOKEN_BUCKET_BOUNDARIES = (1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864)
_operation_input_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=_TOKEN_BUCKET_BOUNDARIES,
)
_operation_output_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=_TOKEN_BUCKET_BOUNDARIES,
)


class _MockServerTransport(httpx2.BaseTransport):
    """Sends each request to the mock server, keeping its path and query."""

    def __init__(self, mock_base_url):
        self._mock = httpx2.URL(mock_base_url)
        self._inner = httpx2.HTTPTransport()

    def handle_request(self, request):
        request.url = request.url.copy_with(scheme=self._mock.scheme, host=self._mock.host, port=self._mock.port)
        request.headers["host"] = self._mock.netloc.decode("ascii")
        return self._inner.handle_request(request)

    def close(self):
        self._inner.close()


def provider_attributes(client):
    """Provider and server attributes, read from the client's configured base_url."""
    base_url = client.base_url
    attributes = {}
    if base_url.host.endswith(OCI_HOST_SUFFIX):
        attributes["gen_ai.provider.name"] = OCI_PROVIDER_NAME
    attributes["server.address"] = base_url.host
    attributes["server.port"] = base_url.port or (443 if base_url.scheme == "https" else 80)
    return attributes


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "meta.llama-3.3-70b-instruct"
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": request_model,
        **provider_attributes(client),
    }
    metric_attributes = dict(span_attributes)
    input_token_count = 0
    output_token_count = 0
    with _reference_tracer.start_as_current_span(
        f"chat {request_model}",
        kind=SpanKind.CLIENT,
        attributes=span_attributes,
        record_exception=False,
    ) as span:
        try:
            messages = [{"role": "user", "content": "Say hello."}]
            resp = client.chat.completions.create(
                model=request_model,
                messages=messages,
            )
            span.set_attribute("gen_ai.response.model", resp.model)
            metric_attributes["gen_ai.response.model"] = resp.model
            span.set_attribute("gen_ai.response.id", resp.id)
            span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
            if resp.usage:
                span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
                if resp.usage.prompt_tokens is not None:
                    input_token_count = resp.usage.prompt_tokens
                if resp.usage.completion_tokens is not None:
                    output_token_count = resp.usage.completion_tokens
            print(f"    -> {resp.choices[0].message.content[:60]}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes["error.type"] = type(e).__qualname__
            raise
        finally:
            _operation_input_tokens.record(input_token_count, metric_attributes)
            _operation_output_tokens.record(output_token_count, metric_attributes)


def main():
    print("=== Reference Implementation: OCI Generative AI (OpenAI-compatible) ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(
        base_url=OCI_BASE_URL,
        api_key="mock-key",
        http_client=httpx2.Client(transport=_MockServerTransport(MOCK_BASE_URL)),
    )

    run_chat_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
