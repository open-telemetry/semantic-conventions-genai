"""Reference implementation for Pydantic AI.

Exercises: chat via OpenAI client
against a mock OpenAI server, with manual OTel spans (no logfire/Agent.instrument_all).
"""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_chat():
    """Scenario: basic chat via Pydantic AI Agent with reference implementation."""
    print("  [chat] basic chat via Pydantic AI Agent (reference implementation)")
    from pydantic_ai import Agent
    from pydantic_ai.messages import TextPart
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    request_temperature = 0.2
    request_top_p = 0.9
    request_max_tokens = 32
    request_seed = 7
    request_stop_sequences = ["###", "<END>"]
    request_frequency_penalty = 0.1
    request_presence_penalty = 0.2
    system_prompt = "You are a helpful assistant."
    prompt_text = "Say hello."
    model = OpenAIChatModel(request_model, provider=provider)
    agent = Agent(model, system_prompt=system_prompt)
    model_settings = {
        "temperature": request_temperature,
        "top_p": request_top_p,
        "max_tokens": request_max_tokens,
        "seed": request_seed,
        "stop_sequences": request_stop_sequences,
        "frequency_penalty": request_frequency_penalty,
        "presence_penalty": request_presence_penalty,
    }
    system_instructions = json.dumps([{"parts": [{"type": "text", "content": system_prompt}]}])

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
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute("gen_ai.request.top_p", request_top_p)
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.request.seed", request_seed)
        span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
        span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
        span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
        span.set_attribute("gen_ai.system_instructions", system_instructions)
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [
                    {"role": "system", "parts": [{"type": "text", "content": system_prompt}]},
                    {"role": "user", "parts": [{"type": "text", "content": prompt_text}]},
                ]
            ),
        )
        result = agent.run_sync(prompt_text, model_settings=model_settings)
        if result.response.model_name:
            span.set_attribute("gen_ai.response.model", result.response.model_name)
        if result.response.provider_response_id:
            span.set_attribute("gen_ai.response.id", result.response.provider_response_id)
        if result.response.finish_reason is not None:
            span.set_attribute(
                "gen_ai.response.finish_reasons",
                [result.response.finish_reason],
            )
        output_parts = [
            {"type": "text", "content": part.content}
            for part in result.response.parts
            if isinstance(part, TextPart) and part.content
        ]
        if output_parts:
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": output_parts,
                            **(
                                {"finish_reason": result.response.finish_reason}
                                if result.response.finish_reason is not None
                                else {}
                            ),
                        }
                    ]
                ),
            )
        usage = result.usage()
        if usage.total_tokens:
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.request.temperature": request_temperature,
            "gen_ai.request.top_p": request_top_p,
            "gen_ai.request.max_tokens": request_max_tokens,
            "gen_ai.request.seed": request_seed,
            "gen_ai.request.stop_sequences": request_stop_sequences,
            "gen_ai.request.frequency_penalty": request_frequency_penalty,
            "gen_ai.request.presence_penalty": request_presence_penalty,
            "gen_ai.system_instructions": system_instructions,
            "gen_ai.input.messages": json.dumps(
                [
                    {"role": "system", "parts": [{"type": "text", "content": system_prompt}]},
                    {"role": "user", "parts": [{"type": "text", "content": prompt_text}]},
                ]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": output_parts,
                        **(
                            {"finish_reason": result.response.finish_reason}
                            if result.response.finish_reason is not None
                            else {}
                        ),
                    }
                ]
            ),
        }
        if result.response.model_name:
            event_attrs["gen_ai.response.model"] = result.response.model_name
        if result.response.provider_response_id:
            event_attrs["gen_ai.response.id"] = result.response.provider_response_id
        if result.response.finish_reason is not None:
            event_attrs["gen_ai.response.finish_reasons"] = [result.response.finish_reason]
        if usage.total_tokens:
            event_attrs["gen_ai.usage.input_tokens"] = usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {str(result.response)[:60]}")


def run_tool_call():
    """Scenario: tool calling via Pydantic AI Agent with reference implementation."""
    print("  [chat_tool_call] tool calling via Pydantic AI Agent (reference implementation)")
    from pydantic_ai import Agent, RunContext, Tool
    from pydantic_ai.messages import TextPart
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    request_temperature = 0.2
    request_top_p = 0.9
    request_max_tokens = 32
    request_seed = 7
    request_stop_sequences = ["###", "<END>"]
    request_frequency_penalty = 0.1
    request_presence_penalty = 0.2
    system_prompt = "You are a helpful assistant."
    prompt_text = "What's the weather in Seattle?"
    model = OpenAIChatModel(request_model, provider=provider)

    def get_weather(ctx: RunContext[None], location: str) -> str:
        """Get the current weather for a location."""
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.description", get_weather.__doc__ or "")
            tool_span.set_attribute("gen_ai.tool.type", "function")
            if ctx.tool_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = "Sunny, 72°F"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
            return result

    tools = [Tool(get_weather)]
    agent = Agent(model, system_prompt=system_prompt, tools=tools, name="weather_agent")
    agent_name = agent.name
    model_settings = {
        "temperature": request_temperature,
        "top_p": request_top_p,
        "max_tokens": request_max_tokens,
        "seed": request_seed,
        "stop_sequences": request_stop_sequences,
        "frequency_penalty": request_frequency_penalty,
        "presence_penalty": request_presence_penalty,
    }
    system_instructions = json.dumps([{"parts": [{"type": "text", "content": system_prompt}]}])

    agent_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent_name,
    }
    with _reference_tracer.start_as_current_span(
        "invoke_agent weather_agent", attributes=agent_span_attributes
    ) as agent_span:
        agent_span.set_attribute("gen_ai.request.temperature", request_temperature)
        agent_span.set_attribute("gen_ai.request.top_p", request_top_p)
        agent_span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        agent_span.set_attribute("gen_ai.request.seed", request_seed)
        agent_span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
        agent_span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
        agent_span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
        agent_span.set_attribute("gen_ai.system_instructions", system_instructions)
        agent_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt_text}]}])
        )
        agent_span.set_attribute(
            "gen_ai.tool.definitions",
            json.dumps(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.function_schema.json_schema,
                        },
                    }
                    for t in tools
                ]
            ),
        )
        host, port = mock_server_host_port(MOCK_BASE_URL)
        span_attributes_2 = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": request_model,
        }
        if host:
            span_attributes_2["server.address"] = host
        if port is not None:
            span_attributes_2["server.port"] = port
        with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
            span.set_attribute("gen_ai.request.temperature", request_temperature)
            span.set_attribute("gen_ai.request.top_p", request_top_p)
            span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
            span.set_attribute("gen_ai.request.seed", request_seed)
            span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
            span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
            span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
            span.set_attribute("gen_ai.system_instructions", system_instructions)
            span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {"role": "system", "parts": [{"type": "text", "content": system_prompt}]},
                        {"role": "user", "parts": [{"type": "text", "content": prompt_text}]},
                    ]
                ),
            )
            span.set_attribute(
                "gen_ai.tool.definitions",
                json.dumps(
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.function_schema.json_schema,
                            },
                        }
                        for t in tools
                    ]
                ),
            )
            result = agent.run_sync(prompt_text, model_settings=model_settings)
            if result.response.model_name:
                span.set_attribute("gen_ai.response.model", result.response.model_name)
            if result.response.provider_response_id:
                span.set_attribute("gen_ai.response.id", result.response.provider_response_id)
            if result.response.finish_reason is not None:
                span.set_attribute(
                    "gen_ai.response.finish_reasons",
                    [result.response.finish_reason],
                )
                agent_span.set_attribute(
                    "gen_ai.response.finish_reasons",
                    [result.response.finish_reason],
                )
            output_parts = [
                {"type": "text", "content": part.content}
                for part in result.response.parts
                if isinstance(part, TextPart) and part.content
            ]
            if output_parts:
                output_messages = json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": output_parts,
                            **(
                                {"finish_reason": result.response.finish_reason}
                                if result.response.finish_reason is not None
                                else {}
                            ),
                        }
                    ]
                )
                span.set_attribute("gen_ai.output.messages", output_messages)
                agent_span.set_attribute("gen_ai.output.messages", output_messages)
            usage = result.usage()
            if usage.total_tokens:
                span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
                agent_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
                agent_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            print(f"    -> {str(result.response)[:60]}")


def main():
    print("=== Reference Implementation: Pydantic AI Reference Implementation ===")

    tp, lp, mp = setup_otel()
    # NO logfire.configure() or Agent.instrument_all() - reference implementation only

    run_chat()
    run_tool_call()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
