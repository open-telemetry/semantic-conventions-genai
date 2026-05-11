"""Reference implementation for Vertex AI.

Exercises: chat, chat_streaming
against a mock Vertex AI server, with manual OTel spans.
"""

import json
import os
import warnings

from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

# The Vertex AI gapic REST transport defaults to HTTPS. Monkey-patch the
# transport to use plain HTTP so we can talk to the local mock server.
from google.cloud.aiplatform_v1.services.prediction_service.transports.rest import (  # noqa: E402
    PredictionServiceRestTransport,
)

_original_rest_init = PredictionServiceRestTransport.__init__


def _patched_rest_init(self, **kwargs):
    kwargs.setdefault("url_scheme", "http")
    return _original_rest_init(self, **kwargs)


PredictionServiceRestTransport.__init__ = _patched_rest_init

_reference_tracer = reference_tracer()


def _mock_host():
    """Return host:port from MOCK_BASE_URL (strip scheme)."""
    return MOCK_BASE_URL.replace("http://", "").replace("https://", "")


def _init_vertexai():
    """Initialize Vertex AI SDK pointing at the mock server."""
    import vertexai
    from google.auth.credentials import AnonymousCredentials

    vertexai.init(
        project="test-project",
        location="us-central1",
        credentials=AnonymousCredentials(),
        api_endpoint=_mock_host(),
        api_transport="rest",
    )


def run_chat():
    """Scenario: basic chat completion with reference implementation."""
    from vertexai.generative_models import GenerativeModel

    print("  [chat] basic chat completion via Vertex AI (reference implementation)")
    request_model = "gemini-2.0-flash"
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.vertex_ai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes) as span:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", UserWarning)
            model = GenerativeModel(request_model)
            prompt_text = "Say hello."
            response = model.generate_content(prompt_text)
        response_model = response.to_dict().get("modelVersion")
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if response.candidates and response.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(response.candidates[0].finish_reason.name)])
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if response.usage_metadata.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage_metadata.prompt_token_count)
            if response.usage_metadata.candidates_token_count:
                span.set_attribute("gen_ai.usage.output_tokens", response.usage_metadata.candidates_token_count)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": prompt_text}]}]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": response.text}],
                        "finish_reason": str(response.candidates[0].finish_reason.name)
                        if response.candidates
                        else None,
                    }
                ]
            ),
        }
        if response_model:
            event_attrs["gen_ai.response.model"] = response_model
        if response.candidates and response.candidates[0].finish_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [str(response.candidates[0].finish_reason.name)]
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if response.usage_metadata.prompt_token_count:
                event_attrs["gen_ai.usage.input_tokens"] = response.usage_metadata.prompt_token_count
            if response.usage_metadata.candidates_token_count:
                event_attrs["gen_ai.usage.output_tokens"] = response.usage_metadata.candidates_token_count
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {response.text[:60]}")


def run_chat_tool_call():
    """Scenario: chat with tool calling with reference implementation."""
    from vertexai.generative_models import FunctionDeclaration, GenerativeModel, Tool

    print("  [chat_tool_call] chat with tool calling via Vertex AI (reference implementation)")
    request_model = "gemini-2.0-flash"
    get_weather_func = FunctionDeclaration(
        name="get_weather",
        description="Get the current weather",
        parameters={
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    )
    tool = Tool(function_declarations=[get_weather_func])
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.vertex_ai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes_2) as span:
        span.set_attribute(
            "gen_ai.tool.definitions",
            json.dumps(
                [
                    {
                        "function_declarations": [
                            {
                                "name": "get_weather",
                                "description": "Get the current weather",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"location": {"type": "string", "description": "City name"}},
                                    "required": ["location"],
                                },
                            }
                        ]
                    }
                ]
            ),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", UserWarning)
            model = GenerativeModel(request_model)
            response = model.generate_content(
                "What's the weather in Seattle?",
                tools=[tool],
            )
        response_model = response.to_dict().get("modelVersion")
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if response.candidates and response.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(response.candidates[0].finish_reason.name)])
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if response.usage_metadata.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage_metadata.prompt_token_count)
            if response.usage_metadata.candidates_token_count:
                span.set_attribute("gen_ai.usage.output_tokens", response.usage_metadata.candidates_token_count)
        part = response.candidates[0].content.parts[0]
        if hasattr(part, "function_call") and part.function_call and part.function_call.name:
            print(f"    -> tool_call: {part.function_call.name}")
        else:
            print(f"    -> {response.text[:60]}")


def run_chat_streaming():
    """Scenario: streaming chat completion with reference implementation."""
    from vertexai.generative_models import GenerativeModel

    print("  [chat_streaming] streaming chat completion via Vertex AI (reference implementation)")
    request_model = "gemini-2.0-flash"
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.vertex_ai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes_3) as span:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", UserWarning)
            model = GenerativeModel(request_model)
            text = ""
            last_chunk = None
            for chunk in model.generate_content("Tell me a joke.", stream=True):
                text += chunk.text
                last_chunk = chunk
        if last_chunk:
            response_model = last_chunk.to_dict().get("modelVersion")
            if response_model:
                span.set_attribute("gen_ai.response.model", response_model)
        if last_chunk and last_chunk.candidates and last_chunk.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(last_chunk.candidates[0].finish_reason.name)])
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            if last_chunk.usage_metadata.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", last_chunk.usage_metadata.prompt_token_count)
            if last_chunk.usage_metadata.candidates_token_count:
                span.set_attribute("gen_ai.usage.output_tokens", last_chunk.usage_metadata.candidates_token_count)
        print(f"    -> {text[:60]}")


def main():
    print("=== Reference Implementation: Vertex AI ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only
    _init_vertexai()

    run_chat()
    run_chat_tool_call()
    run_chat_streaming()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
