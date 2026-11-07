"""Reference scenario for Ollama semantic conventions.

This scenario demonstrates the use of Ollama-specific semantic conventions
for tracing Ollama API calls using standard GenAI span types.
"""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Initialize tracing
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Get tracer
tracer = trace.get_tracer(__name__)


class MockOllamaClient:
    """Mock Ollama client for demonstration purposes."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        repeat_penalty: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Mock chat completion using standard GenAI span type."""
        with tracer.start_as_current_span(
            "gen_ai.client.inference",
            kind=trace.SpanKind.CLIENT,
        ) as span:
            # Set required attributes
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.provider.name", "Ollama")
            span.set_attribute("gen_ai.request.model", model)

            # Set Ollama-specific attributes
            if self.base_url:
                span.set_attribute("ollama.request.base_url", self.base_url)

            # Set generic request attributes
            if stream is not None:
                span.set_attribute("gen_ai.request.stream", stream)

            if temperature is not None:
                span.set_attribute("gen_ai.request.temperature", temperature)

            if top_p is not None:
                span.set_attribute("gen_ai.request.top_p", top_p)

            if top_k is not None:
                span.set_attribute("gen_ai.request.top_k", top_k)

            if max_tokens is not None:
                span.set_attribute("gen_ai.request.max_tokens", max_tokens)

            if stop is not None:
                span.set_attribute("gen_ai.request.stop_sequences", stop)

            if repeat_penalty is not None:
                span.set_attribute("ollama.request.repeat_penalty", repeat_penalty)

            if seed is not None:
                span.set_attribute("gen_ai.request.seed", seed)

            # Set server attributes
            if self.base_url:
                try:
                    from urllib.parse import urlparse
                    url = urlparse(self.base_url)
                    span.set_attribute("server.address", url.hostname)
                    span.set_attribute("server.port", url.port or 80)
                except Exception:
                    pass

            # Simulate response
            response = {
                "model": model,
                "response": "This is a mock response from Ollama.",
                "done": True,
                "total_duration": 1500000000,
                "load_duration": 500000000,
                "prompt_eval_count": 25,
                "eval_count": 100,
            }

            # Set response attributes
            span.set_attribute("gen_ai.response.model", response["model"])
            span.set_attribute("ollama.response.model", response["model"])
            span.set_attribute("ollama.response.total_duration", response["total_duration"])
            span.set_attribute("ollama.response.load_duration", response["load_duration"])
            span.set_attribute("ollama.response.prompt_eval_count", response["prompt_eval_count"])
            span.set_attribute("ollama.response.eval_count", response["eval_count"])
            span.set_attribute("gen_ai.usage.input_tokens", 25)
            span.set_attribute("gen_ai.usage.output_tokens", 100)
            span.set_attribute("gen_ai.response.finish_reason", "stop")

        return response

    def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        repeat_penalty: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Mock text generation using standard GenAI span type."""
        with tracer.start_as_current_span(
            "gen_ai.client.inference",
            kind=trace.SpanKind.CLIENT,
        ) as span:
            # Set required attributes
            span.set_attribute("gen_ai.operation.name", "text_completion")
            span.set_attribute("gen_ai.provider.name", "Ollama")
            span.set_attribute("gen_ai.request.model", model)

            # Set Ollama-specific attributes
            if self.base_url:
                span.set_attribute("ollama.request.base_url", self.base_url)

            # Set generic request attributes
            if stream is not None:
                span.set_attribute("gen_ai.request.stream", stream)

            if temperature is not None:
                span.set_attribute("gen_ai.request.temperature", temperature)

            if top_p is not None:
                span.set_attribute("gen_ai.request.top_p", top_p)

            if top_k is not None:
                span.set_attribute("gen_ai.request.top_k", top_k)

            if max_tokens is not None:
                span.set_attribute("gen_ai.request.max_tokens", max_tokens)

            if stop is not None:
                span.set_attribute("gen_ai.request.stop_sequences", stop)

            if repeat_penalty is not None:
                span.set_attribute("ollama.request.repeat_penalty", repeat_penalty)

            if seed is not None:
                span.set_attribute("gen_ai.request.seed", seed)

            # Set server attributes
            if self.base_url:
                try:
                    from urllib.parse import urlparse
                    url = urlparse(self.base_url)
                    span.set_attribute("server.address", url.hostname)
                    span.set_attribute("server.port", url.port or 80)
                except Exception:
                    pass

            # Simulate response
            response = {
                "model": model,
                "response": "This is a mock text generation response.",
                "done": True,
                "total_duration": 2000000000,
                "load_duration": 600000000,
                "prompt_eval_count": 10,
                "eval_count": 50,
            }

            # Set response attributes
            span.set_attribute("gen_ai.response.model", response["model"])
            span.set_attribute("ollama.response.model", response["model"])
            span.set_attribute("ollama.response.total_duration", response["total_duration"])
            span.set_attribute("ollama.response.load_duration", response["load_duration"])
            span.set_attribute("ollama.response.prompt_eval_count", response["prompt_eval_count"])
            span.set_attribute("ollama.response.eval_count", response["eval_count"])
            span.set_attribute("gen_ai.usage.input_tokens", 10)
            span.set_attribute("gen_ai.usage.output_tokens", 50)
            span.set_attribute("gen_ai.response.finish_reason", "stop")

        return response


def main():
    """Run the reference scenario."""
    client = MockOllamaClient()

    # Test chat completion
    print("Testing Ollama chat completion...")
    client.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        stream=False,
        temperature=0.7,
        top_p=0.9,
        max_tokens=256,
    )

    # Test text generation
    print("Testing Ollama text generation...")
    client.generate(
        model="mistral",
        prompt="Write a short story about a robot.",
        stream=False,
        temperature=0.3,
        max_tokens=100,
    )

    print("Ollama scenario completed successfully!")


if __name__ == "__main__":
    main()
