"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling, a multi-agent run with handoffs wrapped
in a workflow span, and a workflow nested inside another workflow, against a
mock OpenAI server, with manual OTel spans.
"""

import asyncio
import json
import os

import openai
from agents import Agent, RunConfig, Runner, function_tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tool import FunctionTool, ToolContext
from reference_shared import flush_and_shutdown, reference_meter, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"


_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_workflow_inference_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_workflow.inference_calls",
    unit="{inference_call}",
    description="The number of inference (model) calls made during a single GenAI workflow execution.",
)
_workflow_tool_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_workflow.tool_calls",
    unit="{tool_call}",
    description="The number of tool calls made during a single GenAI workflow execution.",
)
_inference_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.inference_calls",
    unit="{inference_call}",
    description="The number of inference (model) calls a GenAI agent makes during a single invocation.",
)
_tool_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.tool_calls",
    unit="{tool_call}",
    description="The number of tool calls a GenAI agent makes during a single invocation.",
)


PROVIDER_HOSTED_ITEM_TYPES = frozenset(
    {
        "file_search_call",
        "web_search_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "program",
    }
)


def _client_side_tool_calls(run_items) -> int:
    """Count the tool calls the model made for client-side execution.

    Counts the call items the model issued, so a tool call that failed is
    still counted, as the convention requires. `ToolCallItem` carries
    client-side and provider-hosted calls alike, and the SDK delivers a raw
    item either parsed or as a plain dict, so both forms are matched on their
    `type`. `HandoffCallItem` is counted too, since a handoff is a tool call
    the model made to route between agents.
    """
    from agents.items import HandoffCallItem, ToolCallItem

    def is_provider_hosted(raw_item) -> bool:
        item_type = raw_item.get("type") if isinstance(raw_item, dict) else getattr(raw_item, "type", None)
        return item_type in PROVIDER_HOSTED_ITEM_TYPES

    return sum(
        isinstance(item, (ToolCallItem, HandoffCallItem)) and not is_provider_hosted(item.raw_item)
        for item in run_items
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

        # One agent and no handoffs, so the run's totals belong to it alone.
        agent_metric_attributes = {"gen_ai.agent.name": agent.name}
        _inference_calls.record(len(result.raw_responses), agent_metric_attributes)
        _tool_calls.record(_client_side_tool_calls(result.new_items), agent_metric_attributes)
        print(f"    -> {str(result.final_output)[:60]}")


async def run_workflow():
    """Run a multi-agent handoff wrapped in a workflow span representing the SDK workflow tracing."""
    from agents import handoff

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    agent_b = Agent(
        name="agent-b",
        instructions="You are agent B, tell the user the weather is sunny.",
        model=model,
    )
    agent_a = Agent(
        name="agent-a",
        instructions="You are agent A. Handoff to agent-b immediately to answer the user's weather question.",
        model=model,
        handoffs=[handoff(agent_b)],
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
        result = await Runner.run(agent_a, input_text, run_config=RunConfig(workflow_name=workflow_name))

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

        # Totals cover every agent the run passed through, so they belong to
        # the workflow grain.
        workflow_metric_attributes = {"gen_ai.workflow.name": workflow_name}
        _workflow_inference_calls.record(len(result.raw_responses), workflow_metric_attributes)
        _workflow_tool_calls.record(_client_side_tool_calls(result.new_items), workflow_metric_attributes)


async def run_nested_workflow():
    """Run a workflow that invokes a second workflow from inside one of its tools.

    `Runner.run` joins an enclosing trace instead of opening a second workflow,
    so this scenario builds the nesting itself by giving the outer agent a tool
    that runs another agent under its own workflow name.
    """
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    researcher = Agent(
        name="researcher",
        instructions="Research the user's question using the tools you have.",
        model=model,
        tools=[get_weather],
    )
    inner_workflow_name = "web_research"
    inner_result = None

    @function_tool(name_override="web_research", description_override="Research a question end to end.")
    async def web_research(question: str) -> str:
        """Run the inner workflow and return its answer to the outer agent."""
        nonlocal inner_result
        inner_span_attributes = {"gen_ai.operation.name": "invoke_workflow"}
        with _reference_tracer.start_as_current_span(
            f"invoke_workflow {inner_workflow_name}", attributes=inner_span_attributes
        ) as inner_span:
            inner_span.set_attribute("gen_ai.workflow.name", inner_workflow_name)
            inner_result = await Runner.run(
                researcher, question, run_config=RunConfig(workflow_name=inner_workflow_name)
            )
            inner_metric_attributes = {"gen_ai.workflow.name": inner_workflow_name}
            _workflow_inference_calls.record(len(inner_result.raw_responses), inner_metric_attributes)
            _workflow_tool_calls.record(_client_side_tool_calls(inner_result.new_items), inner_metric_attributes)

            # No handoffs here, so the run stays with the researcher and
            # its totals belong to that one agent.
            agent_metric_attributes = {"gen_ai.agent.name": researcher.name}
            _inference_calls.record(len(inner_result.raw_responses), agent_metric_attributes)
            _tool_calls.record(_client_side_tool_calls(inner_result.new_items), agent_metric_attributes)
            return str(inner_result.final_output)

    planner = Agent(
        name="planner",
        instructions="Plan the work and delegate research to the web_research tool.",
        model=model,
        tools=[web_research],
    )
    input_text = "What's the weather in Seattle?"

    print("  [nested_workflow_run] workflow nested inside a workflow (reference implementation)")
    outer_workflow_name = "research_assistant"
    outer_span_attributes = {"gen_ai.operation.name": "invoke_workflow"}
    with _reference_tracer.start_as_current_span(
        f"invoke_workflow {outer_workflow_name}", attributes=outer_span_attributes
    ) as outer_span:
        outer_span.set_attribute("gen_ai.workflow.name", outer_workflow_name)
        outer_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )
        result = await Runner.run(planner, input_text, run_config=RunConfig(workflow_name=outer_workflow_name))
        if result.final_output:
            outer_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": str(result.final_output)}]}]),
            )

        # The outer RunResult does not include the inner run, so the
        # enclosing workflow adds the inner counts to its own.
        outer_metric_attributes = {"gen_ai.workflow.name": outer_workflow_name}
        outer_inference = len(result.raw_responses)
        outer_tools = _client_side_tool_calls(result.new_items)
        if inner_result is not None:
            outer_inference += len(inner_result.raw_responses)
            outer_tools += _client_side_tool_calls(inner_result.new_items)
        _workflow_inference_calls.record(outer_inference, outer_metric_attributes)
        _workflow_tool_calls.record(outer_tools, outer_metric_attributes)

        planner_metric_attributes = {"gen_ai.agent.name": planner.name}
        _inference_calls.record(len(result.raw_responses), planner_metric_attributes)
        _tool_calls.record(_client_side_tool_calls(result.new_items), planner_metric_attributes)
        print(f"    -> {str(result.final_output)[:60]}")


def main():
    print("=== Reference Implementation: OpenAI Agents Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent())
    asyncio.run(run_workflow())
    asyncio.run(run_nested_workflow())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
