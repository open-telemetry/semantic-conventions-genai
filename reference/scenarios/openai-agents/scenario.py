"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling
against a mock OpenAI server, with manual OTel spans.
"""

import asyncio
import json
import os

from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


async def run_agent():
    """Run a simple agent with the OpenAI Agents SDK, with manual spans."""
    import openai
    from agents import Agent, Runner, function_tool
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from agents.tool import FunctionTool, ToolContext

    @function_tool
    def get_weather(ctx: ToolContext[None], location: str) -> str:
        """Get the current weather for a location."""
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.description", get_weather.description)
            tool_span.set_attribute("gen_ai.tool.type", "function")
            tool_span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = "Sunny, 72°F"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
            return result

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    tools = [get_weather]
    captured_responses = []
    host, port = mock_server_host_port(MOCK_BASE_URL)
    agent = Agent(
        name="test-agent",
        instructions="You are a helpful assistant.",
        model=model,
        tools=tools,
    )
    input_text = "What's the weather in Seattle?"

    print("  [agent_run] agent with tool calling (reference implementation)")
    agent_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent.name,
    }
    if host:
        agent_span_attributes["server.address"] = host
    if port is not None:
        agent_span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "invoke_agent test-agent", attributes=agent_span_attributes
    ) as agent_span:
        agent_span.set_attribute(
            "gen_ai.system_instructions", json.dumps([{"parts": [{"type": "text", "content": agent.instructions}]}])
        )
        agent_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )
        agent_span.set_attribute(
            "gen_ai.tool.definitions",
            json.dumps(
                [
                    {
                        "type": "function",
                        "function": {"name": t.name, "description": t.description, "parameters": t.params_json_schema},
                    }
                    for t in tools
                    if isinstance(t, FunctionTool)
                ]
            ),
        )
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
            span.set_attribute(
                "gen_ai.tool.definitions",
                json.dumps(
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.params_json_schema,
                            },
                        }
                        for t in tools
                        if isinstance(t, FunctionTool)
                    ]
                ),
            )
            original_create = client.chat.completions.create

            async def _capture_create(*args, **kwargs):
                response = await original_create(*args, **kwargs)
                captured_responses.append(response)
                return response

            client.chat.completions.create = _capture_create
            try:
                result = await Runner.run(agent, input_text)
            finally:
                client.chat.completions.create = original_create
            usage = result.context_wrapper.usage
            if usage.total_tokens:
                span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
                agent_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
                agent_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            if captured_responses:
                last_response = captured_responses[-1]
                if getattr(last_response, "id", None):
                    span.set_attribute("gen_ai.response.id", last_response.id)
                if getattr(last_response, "model", None):
                    span.set_attribute("gen_ai.response.model", last_response.model)
                finish_reasons = [
                    choice.finish_reason
                    for choice in getattr(last_response, "choices", []) or []
                    if getattr(choice, "finish_reason", None)
                ]
                if finish_reasons:
                    agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
            if result.final_output:
                agent_span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": str(result.final_output)}],
                            }
                        ]
                    ),
                )
            print(f"    -> {str(result.final_output)[:60]}")


def main():
    print("=== Reference Implementation: OpenAI Agents Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
