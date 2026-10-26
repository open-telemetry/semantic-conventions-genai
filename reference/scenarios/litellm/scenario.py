"""Reference implementation for LiteLLM.

Exercises: chat, responses, chat_streaming, chat_tool_call, embeddings
against a mock OpenAI server, with manual OTel spans.
"""

import json
import math
import os
import time
from urllib.parse import urlparse

from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_meter, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
_SERVER_ADDRESS = urlparse(os.environ["MOCK_LLM_URL"]).hostname
_SERVER_PORT = urlparse(os.environ["MOCK_LLM_URL"]).port

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_cost_histogram = _reference_meter.create_histogram(
    name="gen_ai.client.operation.cost",
    unit="{cost}",
    description="Monetary cost of a single GenAI inference operation.",
)

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
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat gpt-4o-mini", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
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
                    }
                    for choice in resp.choices
                    if choice.message.content
                ]
            ),
        )
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)

        # Cost: LiteLLM computes per-request cost from its internal pricing table
        response_cost = resp._hidden_params.get("response_cost")
        if response_cost is not None:
            span.set_attribute("gen_ai.usage.cost.amount", response_cost)
            span.set_attribute("gen_ai.usage.cost.currency", "USD")
            span.set_attribute("gen_ai.usage.cost.source", "local")
            _cost_histogram.record(
                response_cost,
                attributes={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": provider_name,
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                    "gen_ai.usage.cost.currency": "USD",
                    "gen_ai.usage.cost.source": "local",
                },
            )

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider_name,
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


def run_responses_cost_breakdown():
    """Scenario: Responses API call whose usage includes cache and reasoning tokens."""
    import litellm
    from litellm.litellm_core_utils.llm_cost_calc.utils import get_token_type_cost_breakdown
    from litellm.responses.utils import ResponseAPILoggingUtils

    print("  [responses] Responses API call via LiteLLM with per-class cost (reference implementation)")
    request_model = "gpt-4o-mini"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    request_messages = [{"role": "user", "content": "Say hello."}]
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat gpt-4o-mini", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        resp = litellm.responses(
            model=litellm_model,
            input=request_messages,
            api_base=MOCK_BASE_URL,
            api_key="mock-key",
        )
        # Every value set on the span is also kept for the details event so the two stay
        # identical. The span is written at each step, so a later failure keeps earlier values.
        response_attrs = {"gen_ai.response.model": resp.model, "gen_ai.response.id": resp.id}
        span.set_attributes(response_attrs)
        usage = ResponseAPILoggingUtils._transform_response_api_usage_to_chat_usage(resp.usage)
        usage_attrs = {
            "gen_ai.usage.input_tokens": usage.prompt_tokens,
            "gen_ai.usage.output_tokens": usage.completion_tokens,
        }
        for key, value in (
            ("gen_ai.usage.cache_read.input_tokens", usage.prompt_tokens_details.cached_tokens),
            ("gen_ai.usage.cache_write.input_tokens", usage.prompt_tokens_details.cache_creation_tokens),
            ("gen_ai.usage.reasoning.output_tokens", usage.completion_tokens_details.reasoning_tokens),
        ):
            if value:
                usage_attrs[key] = value
        span.set_attributes(usage_attrs)
        response_attrs.update(usage_attrs)

        # LiteLLM computes the total from its pricing table. Its prompt cost includes cache
        # reads and writes and its completion cost includes reasoning, so subtract those to
        # keep the classes disjoint.
        response_cost = resp._hidden_params.get("response_cost")
        if response_cost is not None:
            cost_attrs = {
                "gen_ai.usage.cost.amount": response_cost,
                "gen_ai.usage.cost.currency": "USD",
                "gen_ai.usage.cost.source": "local",
            }
            span.set_attributes(cost_attrs)
            response_attrs.update(cost_attrs)
            _cost_histogram.record(
                response_cost,
                attributes={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": provider_name,
                    "gen_ai.request.model": request_model,
                    "gen_ai.response.model": resp.model,
                    "server.address": _SERVER_ADDRESS,
                    "server.port": _SERVER_PORT,
                    "gen_ai.usage.cost.currency": "USD",
                    "gen_ai.usage.cost.source": "local",
                },
            )
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=request_model, custom_llm_provider=provider_name, usage_object=usage
            )
            # The classes are only a breakdown of the amount if LiteLLM applied no discount
            # or margin on top of its token costs.
            if math.isclose(prompt_cost + completion_cost, response_cost):
                token_classes = get_token_type_cost_breakdown(
                    model=request_model, custom_llm_provider=provider_name, usage=usage
                )
                cost_classes = {
                    "gen_ai.usage.cost.input": prompt_cost
                    - token_classes.cache_read_cost
                    - token_classes.cache_creation_cost,
                    "gen_ai.usage.cost.cache_read": token_classes.cache_read_cost,
                    "gen_ai.usage.cost.cache_write": token_classes.cache_creation_cost,
                    "gen_ai.usage.cost.output": completion_cost - token_classes.reasoning_cost,
                    "gen_ai.usage.cost.reasoning": token_classes.reasoning_cost,
                }
                class_attrs = {key: value for key, value in cost_classes.items() if value > 0}
                span.set_attributes(class_attrs)
                response_attrs.update(class_attrs)

        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes={**span_attributes, **response_attrs},
        )
        print(f"    -> cost: {response_cost}")


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
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat gpt-4o-mini", kind=SpanKind.CLIENT, attributes=span_attributes_2
    ) as span:
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
        seen_choice_indexes = set()
        finish_reasons_by_index = {}
        response_id = None
        response_model = None
        for chunk in resp:
            response_id = response_id or chunk.id
            response_model = response_model or chunk.model
            for choice in chunk.choices:
                seen_choice_indexes.add(choice.index)
                if choice.index == 0 and choice.delta.content:
                    text += choice.delta.content
                if choice.finish_reason is not None:
                    finish_reasons_by_index[choice.index] = choice.finish_reason
        if seen_choice_indexes:
            span.set_attribute(
                "gen_ai.response.finish_reasons",
                [finish_reasons_by_index.get(index, "error") for index in range(max(seen_choice_indexes) + 1)],
            )
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        span.set_attribute(
            "gen_ai.output.messages",
            json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": text}],
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
        "server.address": _SERVER_ADDRESS,
    }
    with _reference_tracer.start_as_current_span(
        "chat gpt-4o-mini", kind=SpanKind.CLIENT, attributes=span_attributes_3
    ) as span:
        span.set_attribute(
            "gen_ai.tool.definitions", json.dumps([{"type": t["type"], **t["function"]} for t in [request_tool]])
        )
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
            # LiteLLM returns the tool call; running it is app code LiteLLM never
            # sees, so there is no execute_tool span to emit here.
            print(f"    -> tool_call: {tool_calls[0].function.name}")
        else:
            print(f"    -> {resp.choices[0].message.content[:60]}")


def run_embeddings():
    """Scenario: embedding generation with reference implementation."""
    import litellm

    print("  [embeddings] embedding generation via LiteLLM (reference implementation)")
    request_model = "text-embedding-3-small"
    litellm_model = f"openai/{request_model}"
    provider_name = _provider_name(litellm_model)
    encoding_format = "float"
    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": request_model,
        "server.address": _SERVER_ADDRESS,
    }
    start_time = time.perf_counter()
    metric_attributes = dict(span_attributes_4)
    input_token_count = 0
    with _reference_tracer.start_as_current_span(
        "embeddings text-embedding-3-small",
        kind=SpanKind.CLIENT,
        attributes=span_attributes_4,
        record_exception=False,
    ) as span:
        try:
            span.set_attribute("gen_ai.request.encoding_formats", [encoding_format])
            resp = litellm.embedding(
                model=litellm_model,
                input=["Hello, world!"],
                encoding_format=encoding_format,
                api_base=MOCK_BASE_URL,
                api_key="mock-key",
            )
            if resp.model:
                span.set_attribute("gen_ai.response.model", resp.model)
                metric_attributes["gen_ai.response.model"] = resp.model
            if resp.data and resp.data[0].get("embedding"):
                span.set_attribute("gen_ai.embeddings.dimension.count", len(resp.data[0]["embedding"]))
            if resp.usage:
                span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
                input_token_count = resp.usage.prompt_tokens
            print(f"    -> embedding dim: {len(resp.data[0]['embedding'])}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes["error.type"] = type(e).__qualname__
            raise
        finally:
            _embeddings_duration.record(time.perf_counter() - start_time, metric_attributes)
            _embeddings_input_tokens.record(input_token_count, metric_attributes)


def main():
    print("=== Reference Implementation: LiteLLM ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    run_chat()
    run_responses_cost_breakdown()
    run_chat_streaming()
    run_chat_tool_call()
    run_embeddings()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
