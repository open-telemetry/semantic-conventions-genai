"""Reference implementation for AutoGen."""

import asyncio
import contextlib
import contextvars
import json
import os
import time

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()
_current_tool_call_id = contextvars.ContextVar("autogen_tool_call_id", default=None)


def run_agent_reference():
    """Scenario: basic agent execution via AutoGen with reference implementation."""
    from autogen_agentchat.agents import AssistantAgent, _base_chat_agent
    from autogen_core.tools import _base as _tool_base
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    print("  [agent_run] basic AutoGen agent execution (reference implementation)")

    request_model = "gpt-4o-mini"
    request_seed = 7
    request_max_tokens = 96
    request_temperature = 0.35
    request_top_p = 0.85
    request_stop_sequences = ["<END>"]
    request_frequency_penalty = 0.2
    request_presence_penalty = 0.1
    system_message = "You are a helpful assistant."
    input_text = "What's the weather in Seattle?"
    captured_results = []

    async def get_weather(location: str) -> str:
        """Get the current weather."""
        tool_call_id = _current_tool_call_id.get()
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.description", get_weather.__doc__ or "")
            tool_span.set_attribute("gen_ai.tool.type", "function")
            if tool_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = f"Sunny in {location}"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
            return result

    tool_defs = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        }
    ]
    model_client = OpenAIChatCompletionClient(
        model=request_model,
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
        seed=request_seed,
        max_tokens=request_max_tokens,
        temperature=request_temperature,
        top_p=request_top_p,
        stop=request_stop_sequences,
        frequency_penalty=request_frequency_penalty,
        presence_penalty=request_presence_penalty,
    )

    previous_create_agent_span = _base_chat_agent.trace_create_agent_span
    previous_invoke_agent_span = _base_chat_agent.trace_invoke_agent_span
    previous_tool_span = _tool_base.trace_tool_span

    def _disabled_autogen_span(*_args, **_kwargs):
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def _capture_tool_call_id(*_args, tool_call_id=None, **_kwargs):
        token = _current_tool_call_id.set(tool_call_id)
        try:
            yield None
        finally:
            _current_tool_call_id.reset(token)

    _base_chat_agent.trace_create_agent_span = _disabled_autogen_span
    _base_chat_agent.trace_invoke_agent_span = _disabled_autogen_span
    _tool_base.trace_tool_span = _capture_tool_call_id

    try:
        agent_name = "test_agent"
        agent_description = "Reference AutoGen assistant."
        host, port = mock_server_host_port(MOCK_BASE_URL)
        span_attributes_2 = {
            "gen_ai.operation.name": "create_agent",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": request_model,
            "gen_ai.agent.name": agent_name,
        }
        if host:
            span_attributes_2["server.address"] = host
        if port is not None:
            span_attributes_2["server.port"] = port
        with _reference_tracer.start_as_current_span("create_agent test_agent", attributes=span_attributes_2) as span:
            span.set_attribute("gen_ai.agent.description", agent_description)
            span.set_attribute(
                "gen_ai.system_instructions", json.dumps([{"parts": [{"type": "text", "content": system_message}]}])
            )
            agent = AssistantAgent(
                name=agent_name,
                model_client=model_client,
                description=agent_description,
                system_message=system_message,
                tools=[get_weather],
                max_tool_iterations=2,
            )
            agent_id = getattr(agent, "id", None)
            if agent_id:
                span.set_attribute("gen_ai.agent.id", str(agent_id))

        async def _run():
            from autogen_agentchat.messages import TextMessage
            from autogen_core import CancellationToken

            agent_span_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": request_model,
                "gen_ai.agent.name": agent.name,
            }
            with _reference_tracer.start_as_current_span(
                "invoke_agent test_agent", attributes=agent_span_attributes
            ) as agent_span:
                agent_span.set_attribute("gen_ai.agent.description", agent.description)
                agent_span.set_attribute("gen_ai.request.seed", request_seed)
                agent_span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
                agent_span.set_attribute("gen_ai.request.temperature", request_temperature)
                agent_span.set_attribute("gen_ai.request.top_p", request_top_p)
                agent_span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                agent_span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                agent_span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                agent_span.set_attribute(
                    "gen_ai.system_instructions", json.dumps([{"parts": [{"type": "text", "content": system_message}]}])
                )
                agent_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                agent_span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
                host, port = mock_server_host_port(MOCK_BASE_URL)
                span_attributes_3 = {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "openai",
                    "gen_ai.request.model": request_model,
                }
                if host:
                    span_attributes_3["server.address"] = host
                if port is not None:
                    span_attributes_3["server.port"] = port
                with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_3) as span:
                    span.set_attribute("gen_ai.request.seed", request_seed)
                    span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
                    span.set_attribute("gen_ai.request.temperature", request_temperature)
                    span.set_attribute("gen_ai.request.top_p", request_top_p)
                    span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                    span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                    span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                    span.set_attribute(
                        "gen_ai.system_instructions",
                        json.dumps([{"parts": [{"type": "text", "content": system_message}]}]),
                    )
                    span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                    )
                    span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
                    original_create = model_client.create

                    async def _capture_create(messages, **kwargs):
                        result = await original_create(messages, **kwargs)
                        captured_results.append(result)
                        return result

                    model_client.create = _capture_create
                    try:
                        response = await agent.on_messages(
                            [TextMessage(content=input_text, source="user")],
                            cancellation_token=CancellationToken(),
                        )
                    finally:
                        model_client.create = original_create
                    finish_reasons = [result.finish_reason for result in captured_results if result.finish_reason]
                    if finish_reasons:
                        agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
                    if captured_results:
                        last_result = captured_results[-1]
                        if getattr(last_result, "model", None):
                            agent_span.set_attribute("gen_ai.response.model", last_result.model)
                        if getattr(last_result, "id", None):
                            agent_span.set_attribute("gen_ai.response.id", last_result.id)
                    total_input_tokens = sum(
                        result.usage.prompt_tokens
                        for result in captured_results
                        if getattr(result, "usage", None) is not None
                    )
                    total_output_tokens = sum(
                        result.usage.completion_tokens
                        for result in captured_results
                        if getattr(result, "usage", None) is not None
                    )
                    if total_input_tokens:
                        agent_span.set_attribute("gen_ai.usage.input_tokens", total_input_tokens)
                    if total_output_tokens:
                        agent_span.set_attribute("gen_ai.usage.output_tokens", total_output_tokens)
                    output_messages = json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": str(response.chat_message.content)}],
                            }
                        ]
                    )
                    span.set_attribute(
                        "gen_ai.output.messages",
                        output_messages,
                    )
                    agent_span.set_attribute(
                        "gen_ai.output.messages",
                        output_messages,
                    )
                    event_attrs = {
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.request.model": request_model,
                        "gen_ai.system_instructions": json.dumps(
                            [{"parts": [{"type": "text", "content": system_message}]}]
                        ),
                        "gen_ai.input.messages": json.dumps(
                            [
                                {"role": "user", "parts": [{"type": "text", "content": input_text}]},
                            ]
                        ),
                        "gen_ai.output.messages": output_messages,
                    }
                    if finish_reasons:
                        event_attrs["gen_ai.response.finish_reasons"] = finish_reasons
                    if total_input_tokens:
                        event_attrs["gen_ai.usage.input_tokens"] = total_input_tokens
                    if total_output_tokens:
                        event_attrs["gen_ai.usage.output_tokens"] = total_output_tokens
                    if host:
                        event_attrs["server.address"] = host
                    if port is not None:
                        event_attrs["server.port"] = port
                    reference_event_logger().emit(
                        event_name="gen_ai.client.inference.operation.details",
                        body="Inference operation details",
                        attributes=event_attrs,
                    )
                    print(f"    -> {str(response.chat_message.content)[:60]}")

        asyncio.run(_run())
    finally:
        _base_chat_agent.trace_create_agent_span = previous_create_agent_span
        _base_chat_agent.trace_invoke_agent_span = previous_invoke_agent_span
        _tool_base.trace_tool_span = previous_tool_span


def run_chat_tool_call_reference():
    """Scenario: chat with tool calling with reference implementation."""
    import openai

    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "gpt-4o-mini"
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
    tools = [request_tool]

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        resp = client.chat.completions.create(
            model=request_model,
            messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
            tools=tools,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        choice = resp.choices[0]
        if choice.message.tool_calls:
            print(f"    -> tool_call: {choice.message.tool_calls[0].function.name}")
        else:
            print(f"    -> {choice.message.content[:60]}")


def main():
    print("=== Reference Implementation: AutoGen Reference Implementation ===")

    tp, lp, mp = setup_otel()

    run_agent_reference()
    run_chat_tool_call_reference()

    time.sleep(2)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
