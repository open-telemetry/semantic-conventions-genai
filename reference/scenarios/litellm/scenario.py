"""Reference implementation for LiteLLM.

Exercises: chat, chat_streaming, chat_tool_call, embeddings
against a mock OpenAI server, with manual OTel spans.
"""

import json
import os

from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def _provider_name(model_name: str) -> str:
    provider, _, _ = model_name.partition("/")
    return provider or model_name


def run_chat():
    """Scenario: basic chat completion with reference implementation."""
    import litellm

    print("  [chat] basic chat completion via LiteLLM (reference implementation)")
    request_model = "gpt-4o-mini"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    prompt_text = "Say hello."
    request_messages = [{"role": "user", "content": prompt_text}]
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [
                    {"role": message["role"], "parts": [{"type": "text", "content": message["content"]}]}
                    for message in request_messages
                ]
            ),
        )
        resp = litellm.completion(
            model=litellm_model,
            messages=request_messages,
            api_base=MOCK_BASE_URL,
            api_key="mock-key",
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        span.set_attribute(
            "gen_ai.output.messages",
            json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": choice.message.content}],
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in resp.choices
                    if choice.message.content
                ]
            ),
        )
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [c.finish_reason for c in resp.choices],
            "gen_ai.input.messages": json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in request_messages]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": c.message.content}],
                        "finish_reason": c.finish_reason,
                    }
                    for c in resp.choices
                    if c.message.content
                ]
            ),
        }
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.prompt_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.completion_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_chat_streaming():
    """Scenario: streaming chat completion with reference implementation."""
    import litellm

    print("  [chat_streaming] streaming chat via LiteLLM (reference implementation)")
    request_model = "gpt-4o-mini"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    prompt_text = "Tell me a joke."
    request_messages = [{"role": "user", "content": prompt_text}]
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [
                    {"role": message["role"], "parts": [{"type": "text", "content": message["content"]}]}
                    for message in request_messages
                ]
            ),
        )
        resp = litellm.completion(
            model=litellm_model,
            messages=request_messages,
            api_base=MOCK_BASE_URL,
            api_key="mock-key",
            stream=True,
        )
        text = ""
        finish_reason = None
        for chunk in resp:
            if chunk.choices[0].delta.content:
                text += chunk.choices[0].delta.content
            if chunk.choices[0].finish_reason is not None:
                finish_reason = chunk.choices[0].finish_reason
        span.set_attribute(
            "gen_ai.output.messages",
            json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": text}],
                        **({"finish_reason": finish_reason} if finish_reason is not None else {}),
                    }
                ]
            ),
        )
        print(f"    -> {text[:60]}")


def run_chat_tool_call():
    """Scenario: chat with tool calling with reference implementation."""
    import litellm

    print("  [chat_tool_call] chat with tool calling via LiteLLM (reference implementation)")
    request_model = "gpt-4o-mini"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    request_messages = [{"role": "user", "content": "What's the weather in Seattle?"}]
    request_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    }

    def get_weather(location: str) -> str:
        return f"Sunny in {location}"

    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_3) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps([request_tool]))
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [
                    {"role": message["role"], "parts": [{"type": "text", "content": message["content"]}]}
                    for message in request_messages
                ]
            ),
        )
        resp = litellm.completion(
            model=litellm_model,
            messages=request_messages,
            tools=[request_tool],
            api_base=MOCK_BASE_URL,
            api_key="mock-key",
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        tool_calls = getattr(resp.choices[0].message, "tool_calls", None)
        if tool_calls:
            tool_call = tool_calls[0]
            arguments_json = tool_call.function.arguments or "{}"
            arguments = json.loads(arguments_json)
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
            }
            with _reference_tracer.start_as_current_span(
                "execute_tool get_weather", attributes=tool_span_attributes
            ) as tool_span:
                tool_span.set_attribute("gen_ai.tool.name", tool_call.function.name)
                tool_span.set_attribute("gen_ai.tool.description", request_tool["function"]["description"])
                tool_span.set_attribute("gen_ai.tool.type", request_tool["type"])
                if getattr(tool_call, "id", None):
                    tool_span.set_attribute("gen_ai.tool.call.id", tool_call.id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
                result = get_weather(arguments.get("location", "unknown"))
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            print(f"    -> tool_call: {tool_call.function.name}")
        else:
            print(f"    -> {resp.choices[0].message.content[:60]}")


def run_embeddings():
    """Scenario: embedding generation with reference implementation."""
    import litellm

    print("  [embeddings] embedding generation via LiteLLM (reference implementation)")
    request_model = "text-embedding-3-small"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span(
        "embeddings text-embedding-3-small", attributes=span_attributes_4
    ) as span:
        resp = litellm.embedding(
            model=litellm_model,
            input=["Hello, world!"],
            api_base=MOCK_BASE_URL,
            api_key="mock-key",
        )
        if resp.model:
            span.set_attribute("gen_ai.response.model", resp.model)
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
        print(f"    -> embedding dim: {len(resp.data[0]['embedding'])}")


def main():
    print("=== Reference Implementation: LiteLLM ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    run_chat()
    run_chat_streaming()
    run_chat_tool_call()
    run_embeddings()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
