"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling and a multi-agent run with handoffs
wrapped in a workflow span, against a mock OpenAI server, with manual OTel spans.
"""

import asyncio
import json
import os

import openai
from agents import Agent, RunConfig, RunHooks, Runner, function_tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tool import FunctionTool, ToolContext
from reference_shared import flush_and_shutdown, reference_meter, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()
# Bucket boundaries advised for each metric by docs/gen-ai/gen-ai-metrics.md.
_workflow_inference_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_workflow.inference_calls",
    unit="{inference_call}",
    description="The number of inference (model) calls made during a single GenAI workflow execution.",
    explicit_bucket_boundaries_advisory=[0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
)
_workflow_tool_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_workflow.tool_calls",
    unit="{tool_call}",
    description="The number of tool calls made during a single GenAI workflow execution.",
    explicit_bucket_boundaries_advisory=[0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
)


@function_tool
def get_weather(ctx: ToolContext[None], location: str) -> str:
    """Get the current weather for a location."""
    tool_span_attributes = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "get_weather",
        "gen_ai.tool.type": "function",
    }
    if ctx.agent is not None and ctx.agent.name:
        tool_span_attributes["gen_ai.agent.name"] = ctx.agent.name
    with _reference_tracer.start_as_current_span(
        "execute_tool get_weather", attributes=tool_span_attributes
    ) as tool_span:
        tool_span.set_attribute("gen_ai.tool.description", get_weather.description)
        tool_span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
        tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
        result = "Sunny, 72°F"
        tool_span.set_attribute("gen_ai.tool.call.result", result)
        return result


async def run_agent():
    """Run a simple agent with the OpenAI Agents SDK, with manual spans."""
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    tools = [get_weather]
    captured_responses = []
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
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent.name,
    }
    with _reference_tracer.start_as_current_span(
        "invoke_agent test-agent", attributes=agent_span_attributes
    ) as agent_span:
        agent_span.set_attribute(
            "gen_ai.system_instructions", json.dumps([{"type": "text", "content": agent.instructions}])
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
            agent_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            agent_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        if captured_responses:
            last_response = captured_responses[-1]
            finish_reasons = [
                getattr(choice, "finish_reason", None) or "error"
                for choice in getattr(last_response, "choices", []) or []
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


async def run_workflow():
    """Run a multi-agent handoff wrapped in a workflow span representing the SDK workflow tracing."""
    from agents import handoff

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    call_counts = {"inference": 0, "tool": 0}

    class WorkflowHooks(RunHooks):
        async def on_llm_start(self, context, agent, system_prompt, input_items):
            # Count before the call, including calls that raise without a response.
            call_counts["inference"] += 1

        async def on_tool_start(self, context, agent, tool):
            # The SDK invokes this hook only for local tools.
            call_counts["tool"] += 1

    agent_b = Agent(
        name="agent-b",
        instructions="You are agent B, tell the user the weather is sunny.",
        model=model,
    )
    handoff_to_b = handoff(agent_b)
    original_handoff = handoff_to_b.on_invoke_handoff

    async def counted_handoff(context, arguments):
        # A handoff routes control between agents and counts as a tool call,
        # but it never reaches on_tool_start. RunHooks.on_handoff only fires
        # once on_invoke_handoff has returned, so counting here is what
        # includes a handoff that raises.
        call_counts["tool"] += 1
        return await original_handoff(context, arguments)

    handoff_to_b.on_invoke_handoff = counted_handoff
    agent_a = Agent(
        name="agent-a",
        instructions="You are agent A. Handoff to agent-b immediately to answer the user's weather question.",
        model=model,
        handoffs=[handoff_to_b],
    )
    input_text = "What's the weather in Seattle?"

    print("  [workflow_run] agent run as workflow (reference implementation)")
    workflow_name = "sequential-agents"
    workflow_span_attributes = {
        "gen_ai.operation.name": "invoke_workflow",
    }
    with _reference_tracer.start_as_current_span(
        f"invoke_workflow {workflow_name}", attributes=workflow_span_attributes
    ) as workflow_span:
        workflow_span.set_attribute("gen_ai.workflow.name", workflow_name)
        workflow_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )

        # Note: Agent spans (invoke_agent) are expected to be children of the
        # workflow span but are omitted for brevity in this scenario.
        try:
            result = await Runner.run(
                agent_a, input_text, run_config=RunConfig(workflow_name=workflow_name), hooks=WorkflowHooks()
            )
        finally:
            workflow_metric_attributes = {"gen_ai.workflow.name": workflow_name}
            _workflow_inference_calls.record(call_counts["inference"], workflow_metric_attributes)
            _workflow_tool_calls.record(call_counts["tool"], workflow_metric_attributes)

        if result.final_output:
            output_messages = json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": str(result.final_output)}],
                    }
                ]
            )
            workflow_span.set_attribute("gen_ai.output.messages", output_messages)
        print(f"    -> {str(result.final_output)[:60]}")


def main():
    print("=== Reference Implementation: OpenAI Agents Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent())
    asyncio.run(run_workflow())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
