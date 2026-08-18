"""Reference implementation for Google GenAI.

Exercises: chat, chat_streaming, embeddings
against a mock Google GenAI server, with manual OTel spans.
"""

import json
import os
from contextlib import contextmanager

from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()


@contextmanager
def _patch_automatic_function_calling():
    """Emit execute_tool spans from the SDK's automatic-function-calling dispatch.

    `_extra_utils.get_function_response_parts` is where the SDK invokes the
    application's callable: the `FunctionCall` (id, name, args) and the callable
    itself are both in scope, so this is the hook generic instrumentation would
    patch. Wrapping the callable instead would lose the tool call id.
    """
    from google.genai import _extra_utils

    original = _extra_utils.get_function_response_parts

    def instrumented(response, function_map):
        parts = []
        candidate = response.candidates[0] if response.candidates else None
        for part in (candidate.content.parts if candidate and candidate.content else None) or []:
            call = part.function_call
            if not call or not call.name:
                continue
            func = function_map.get(call.name)
            if func is None:
                continue
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": call.name,
                "gen_ai.tool.type": "function",
            }
            description = (getattr(func, "__doc__", "") or "").strip().splitlines()
            if description:
                tool_span_attributes["gen_ai.tool.description"] = description[0]
            with _reference_tracer.start_as_current_span(
                f"execute_tool {call.name}", attributes=tool_span_attributes
            ) as tool_span:
                if call.id:
                    tool_span.set_attribute("gen_ai.tool.call.id", call.id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(dict(call.args or {})))
                single = response.model_copy(deep=True)
                single.candidates[0].content.parts = [part]
                result_parts = original(single, function_map)
                for result_part in result_parts:
                    tool_span.set_attribute(
                        "gen_ai.tool.call.result", json.dumps(result_part.function_response.response)
                    )
                parts.extend(result_parts)
        return parts

    _extra_utils.get_function_response_parts = instrumented
    try:
        yield
    finally:
        _extra_utils.get_function_response_parts = original


def run_chat():
    """Scenario: basic chat completion with reference implementation."""
    from google import genai
    from google.genai import types

    print("  [chat] basic chat completion via Google GenAI (reference implementation)")
    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )
    request_model = "gemini-2.0-flash"
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes) as span:
        prompt_text = "Say hello."
        response = client.models.generate_content(
            model=request_model,
            contents=prompt_text,
        )
        if response.model_version:
            span.set_attribute("gen_ai.response.model", response.model_version)
        if response.candidates and response.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(response.candidates[0].finish_reason)])
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if hasattr(response.usage_metadata, "prompt_token_count") and response.usage_metadata.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage_metadata.prompt_token_count)
            if (
                hasattr(response.usage_metadata, "candidates_token_count")
                and response.usage_metadata.candidates_token_count
            ):
                span.set_attribute("gen_ai.usage.output_tokens", response.usage_metadata.candidates_token_count)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "gcp.gemini",
            "gen_ai.request.model": request_model,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": prompt_text}]}]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": response.text}],
                        "finish_reason": str(response.candidates[0].finish_reason) if response.candidates else None,
                    }
                ]
            ),
        }
        if response.model_version:
            event_attrs["gen_ai.response.model"] = response.model_version
        if response.candidates and response.candidates[0].finish_reason:
            event_attrs["gen_ai.response.finish_reasons"] = [str(response.candidates[0].finish_reason)]
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if hasattr(response.usage_metadata, "prompt_token_count") and response.usage_metadata.prompt_token_count:
                event_attrs["gen_ai.usage.input_tokens"] = response.usage_metadata.prompt_token_count
            if (
                hasattr(response.usage_metadata, "candidates_token_count")
                and response.usage_metadata.candidates_token_count
            ):
                event_attrs["gen_ai.usage.output_tokens"] = response.usage_metadata.candidates_token_count
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {response.text[:60]}")


def run_interactions_continuation():
    """Scenario: Google GenAI Interactions API continuation."""
    from google import genai
    from google.genai import types

    print("  [interactions_continuation] interactions continuation via Google GenAI (reference implementation)")
    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )
    request_model = "gemini-2.0-flash"
    initial_interaction = client.interactions.create(
        model=request_model,
        input="Initial prompt.",
    )
    previous_interaction_id = initial_interaction.id

    prompt_text = "Follow up prompt."
    span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": "interactions_agent",
        "gen_ai.request.previous_response.id": previous_interaction_id,
    }
    with _reference_tracer.start_as_current_span(
        "invoke_agent interactions_agent", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        interaction = client.interactions.create(
            model=request_model,
            previous_interaction_id=previous_interaction_id,
            input=prompt_text,
        )
        if interaction.id:
            span.set_attribute("gen_ai.response.id", interaction.id)
        if interaction.model:
            span.set_attribute("gen_ai.response.model", str(interaction.model))
        if interaction.usage:
            if interaction.usage.total_input_tokens:
                span.set_attribute("gen_ai.usage.input_tokens", interaction.usage.total_input_tokens)
            if interaction.usage.total_output_tokens:
                span.set_attribute("gen_ai.usage.output_tokens", interaction.usage.total_output_tokens)

        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "gcp.gemini",
            "gen_ai.request.model": request_model,
            "gen_ai.request.previous_response.id": previous_interaction_id,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": prompt_text}]}]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": "This is a response from the mock interactions server."}],
                        "finish_reason": "stop",
                    }
                ]
            ),
        }
        if interaction.id:
            event_attrs["gen_ai.response.id"] = interaction.id
        if interaction.model:
            event_attrs["gen_ai.response.model"] = str(interaction.model)
        if interaction.usage:
            if interaction.usage.total_input_tokens:
                event_attrs["gen_ai.usage.input_tokens"] = interaction.usage.total_input_tokens
            if interaction.usage.total_output_tokens:
                event_attrs["gen_ai.usage.output_tokens"] = interaction.usage.total_output_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )
        print(f"    -> previous_response_id: {previous_interaction_id}")


def run_chat_tool_call():
    """Scenario: chat with tool calling with reference implementation."""
    from google import genai
    from google.genai import types

    print("  [chat_tool_call] chat with tool calling via Google GenAI (reference implementation)")
    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )
    request_model = "gemini-2.0-flash"

    def get_weather(location: str) -> str:
        """Get the current weather.

        Args:
            location: City name
        """
        return f"Sunny in {location}"

    tools = [get_weather]
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
    }
    with (
        _patch_automatic_function_calling(),
        _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes_2) as span,
    ):
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
        response = client.models.generate_content(
            model=request_model,
            contents="What's the weather in Seattle?",
            config=types.GenerateContentConfig(tools=tools),
        )
        if response.model_version:
            span.set_attribute("gen_ai.response.model", response.model_version)
        if response.candidates and response.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(response.candidates[0].finish_reason)])
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            if hasattr(response.usage_metadata, "prompt_token_count") and response.usage_metadata.prompt_token_count:
                span.set_attribute("gen_ai.usage.input_tokens", response.usage_metadata.prompt_token_count)
            if (
                hasattr(response.usage_metadata, "candidates_token_count")
                and response.usage_metadata.candidates_token_count
            ):
                span.set_attribute("gen_ai.usage.output_tokens", response.usage_metadata.candidates_token_count)
        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if hasattr(part, "function_call") and part.function_call:
                print(f"    -> tool_call: {part.function_call.name}")
            else:
                print(f"    -> {response.text[:60]}")
        else:
            print(f"    -> {response.text[:60]}")


def run_chat_streaming():
    """Scenario: streaming chat completion with reference implementation."""
    from google import genai
    from google.genai import types

    print("  [chat_streaming] streaming chat via Google GenAI (reference implementation)")
    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )
    request_model = "gemini-2.0-flash"
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gemini-2.0-flash", attributes=span_attributes_3) as span:
        text = ""
        last_chunk = None
        for chunk in client.models.generate_content_stream(
            model=request_model,
            contents="Tell me a joke.",
        ):
            if chunk.text:
                text += chunk.text
            last_chunk = chunk
        if last_chunk and last_chunk.model_version:
            span.set_attribute("gen_ai.response.model", last_chunk.model_version)
        if last_chunk and last_chunk.candidates and last_chunk.candidates[0].finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", [str(last_chunk.candidates[0].finish_reason)])
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            if (
                hasattr(last_chunk.usage_metadata, "prompt_token_count")
                and last_chunk.usage_metadata.prompt_token_count
            ):
                span.set_attribute("gen_ai.usage.input_tokens", last_chunk.usage_metadata.prompt_token_count)
            if (
                hasattr(last_chunk.usage_metadata, "candidates_token_count")
                and last_chunk.usage_metadata.candidates_token_count
            ):
                span.set_attribute("gen_ai.usage.output_tokens", last_chunk.usage_metadata.candidates_token_count)
        print(f"    -> {text[:60]}")


def run_embeddings():
    """Scenario: embedding generation with reference implementation."""
    from google import genai
    from google.genai import types

    print("  [embeddings] embedding generation via Google GenAI (reference implementation)")
    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )
    request_model = "text-embedding-004"
    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("embeddings text-embedding-004", attributes=span_attributes_4) as span:
        response = client.models.embed_content(
            model=request_model,
            contents="Hello, world!",
        )
        if response.embeddings and response.embeddings[0].values is not None:
            span.set_attribute("gen_ai.embeddings.dimension.count", len(response.embeddings[0].values))
        print(f"    -> embedding dim: {len(response.embeddings[0].values)}")


def run_create_agent():
    """Scenario: create a remote agent via Google GenAI (`client.agents.create`).

    The agent runs server-side, so only the client operation is instrumentable here.
    """
    from google import genai
    from google.genai import types

    print("  [create_agent] Google GenAI: create agent")
    request_model = "gemini-2.0-flash"
    agent_name = "reference-agent"
    agent_description = "Reference managed agent."
    agent_system = "You are a helpful assistant."

    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(
            base_url=MOCK_BASE_URL,
            api_version="v1beta",
        ),
    )

    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent_name,
    }
    with _reference_tracer.start_as_current_span(
        f"create_agent {agent_name}", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.agent.description", agent_description)
        span.set_attribute("gen_ai.system_instructions", json.dumps([{"type": "text", "content": agent_system}]))
        try:
            agent = client.agents.create(
                id=agent_name,
                description=agent_description,
                system_instruction=agent_system,
            )
            if agent.name:
                span.set_attribute("gen_ai.agent.id", agent.name.split("/")[-1])
            print(f"    -> {agent.name}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def main():
    print("=== Reference Implementation: Google GenAI ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    run_chat()
    run_interactions_continuation()
    run_chat_tool_call()
    run_chat_streaming()
    run_embeddings()
    run_create_agent()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
