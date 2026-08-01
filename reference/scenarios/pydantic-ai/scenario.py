"""Reference implementation for Pydantic AI.

Exercises: agent run with tool calling
against a mock OpenAI server, with manual OTel spans (no logfire/Agent.instrument_all).
"""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


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
            "gen_ai.tool.name": "get_weather",
            "gen_ai.tool.type": "function",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.description", get_weather.__doc__ or "")
            if ctx.agent is not None and ctx.agent.name:
                tool_span.set_attribute("gen_ai.agent.name", ctx.agent.name)
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
    system_instructions = json.dumps([{"type": "text", "content": system_prompt}])

    agent_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
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
        result = agent.run_sync(prompt_text, model_settings=model_settings)
        if result.response.finish_reason is not None:
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
            agent_span.set_attribute("gen_ai.output.messages", output_messages)
        usage = result.usage
        if usage.total_tokens:
            agent_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            agent_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        print(f"    -> {str(result.response)[:60]}")


def main():
    print("=== Reference Implementation: Pydantic AI Reference Implementation ===")

    tp, lp, mp = setup_otel()
    # NO logfire.configure() or Agent.instrument_all() - reference implementation only

    run_tool_call()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
