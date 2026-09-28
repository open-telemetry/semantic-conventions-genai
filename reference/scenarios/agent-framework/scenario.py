"""Native telemetry scenario for Microsoft Agent Framework."""

import asyncio
import os
import time
from typing import Annotated

from reference_shared import flush_and_shutdown, reference_meter, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_meter = reference_meter()
_invoke_agent_duration = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.duration",
    unit="s",
    description="The end-to-end duration of a single in-process agent invocation.",
)


async def run_agent_tool_call():
    """Scenario: Coding-agent definitions with stable, source-qualified IDs."""
    from agent_framework import Agent, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatClient

    print("  [agent_run] coding-agent definitions with stable IDs (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    request_model = "gpt-4o-mini"
    client = OpenAIChatClient(
        model=request_model,
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    agents = [
        Agent(
            client=client,
            id="builtin:weather",
            name="WeatherAgent",
            description="Built-in coding agent that answers weather questions.",
            instructions="You are the built-in weather agent.",
            tools=[get_weather],
        ),
        Agent(
            client=client,
            id="project:weather",
            name="WeatherAgent",
            description="Project coding agent that answers weather questions.",
            instructions="You are the project weather agent.",
            tools=[get_weather],
        ),
    ]

    for agent in agents:
        start_time = time.perf_counter()
        result = await agent.run(
            "What's the weather in Seattle?",
            options={
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 64,
            },
        )
        _invoke_agent_duration.record(
            time.perf_counter() - start_time,
            {
                "gen_ai.agent.id": agent.id,
                "gen_ai.agent.name": agent.name,
                "gen_ai.request.model": request_model,
            },
        )
        print(f"    -> {agent.id}: {result.text[:60]}")


async def run_tool_call():
    """Scenario: Agent Framework chat client tool calling with native telemetry."""
    from agent_framework import Message, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatCompletionClient

    print("  [chat_tool_call] chat client with tool calling (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    response = await client.get_response(
        [Message(role="user", contents=["What's the weather in Seattle?"])],
        options={
            "tools": [get_weather],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 64,
            "seed": 7,
            "stop": ["<END>"],
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        },
    )
    print(f"    -> {response.text[:60]}")


async def run_chat_completion_agent_tool_call():
    """Scenario: Agent Framework agent execution through Chat Completions."""
    from agent_framework import Agent, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatCompletionClient

    print("  [agent_chat_completion] agent with Chat Completions (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    agent = Agent(
        client=client,
        id="builtin:weather-chat-completions",
        name="WeatherAgentChatCompletions",
        description="Answers weather questions with a function tool.",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    result = await agent.run(
        "What's the weather in Seattle?",
        options={
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 64,
            "seed": 7,
            "stop": ["<END>"],
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        },
    )
    print(f"    -> {result.text[:60]}")


async def run_agent_workflow():
    """Scenario: Agent Framework workflow execution with native telemetry."""
    from agent_framework import Agent, WorkflowBuilder
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatClient

    print("  [workflow] two-agent workflow (native telemetry)")

    enable_sensitive_telemetry(force=True)

    client = OpenAIChatClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    writer_agent = Agent(
        client=client,
        name="writer",
        instructions="You are a concise copy writer.",
    )
    reviewer_agent = Agent(
        client=client,
        name="reviewer",
        instructions="You review slogans and suggest one short improvement.",
    )
    workflow = (
        WorkflowBuilder(
            start_executor=writer_agent,
            name="slogan_review_workflow",
            description="Drafts and reviews a short slogan.",
            output_from=[reviewer_agent],
        )
        .add_edge(writer_agent, reviewer_agent)
        .build()
    )

    result = await workflow.run("Create a slogan for a compact electric van.")
    outputs = result.get_outputs()
    if outputs:
        print(f"    -> {str(outputs[0])[:60]}")


def main():
    print("=== Native Telemetry: Microsoft Agent Framework ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent_tool_call())
    asyncio.run(run_tool_call())
    asyncio.run(run_chat_completion_agent_tool_call())
    asyncio.run(run_agent_workflow())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
