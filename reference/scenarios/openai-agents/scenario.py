"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling, agent-as-tool delegation, sandboxed
command execution, and a multi-agent run with handoffs wrapped in a workflow
span, against a mock OpenAI server, with manual OTel spans.
"""

import asyncio
import contextlib
import json
import os
import posixpath

import openai
from agents import Agent, RunConfig, Runner, function_tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tool import FunctionTool, ToolContext
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
# The shell this deployment lets the sandboxed agent run commands with.
SANDBOX_SHELL = "/bin/bash"

_reference_tracer = reference_tracer()


@contextlib.contextmanager
def _patched_method(obj, name, replacement):
    """Temporarily replace the ``obj.name`` bound method with ``replacement`` as
    an instrumentation seam, always restoring the original in ``finally`` --
    including on exceptions. Repo rules allow patching a public or private method
    as a seam as long as the scenario still enters through the library's public
    API; this helper just guarantees the patch is symmetric.
    """
    original = getattr(obj, name)
    setattr(obj, name, replacement)
    try:
        yield
    finally:
        setattr(obj, name, original)


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


async def run_agent_as_tool_delegation():
    """Delegation: a caller agent invokes another agent exposed via `Agent.as_tool`.

    `Agent.as_tool()` runs the target agent as a function tool and returns its
    result to the original agent. The caller-owned `execute_tool` span records
    the transfer; the child `invoke_agent` span records the target's execution.
    """
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    # The target agent has no tools, so its mock model call returns plain text.
    specialist = Agent(
        name="weather-specialist",
        instructions="You report the weather.",
        model=model,
    )
    weather_tool = specialist.as_tool(
        tool_name="weather-specialist",
        tool_description="Delegate weather questions to the weather specialist agent.",
    )

    # Wrap the tool's public invoker to open the caller-owned execute_tool span
    # around the real sub-agent invocation. The entry point stays `Runner.run`;
    # the patched invoker is restored in `finally` by `_patched_method` below.
    original_on_invoke_tool = weather_tool.on_invoke_tool

    async def _traced_on_invoke_tool(tool_context, input_json):
        transfer_attributes = {
            "gen_ai.agent.name": caller.name,
            "gen_ai.transfer.mode": "return_to_caller",
            "gen_ai.transfer.target.name": specialist.name,
        }
        assert transfer_attributes == {
            "gen_ai.agent.name": "assistant",
            "gen_ai.transfer.mode": "return_to_caller",
            "gen_ai.transfer.target.name": "weather-specialist",
        }
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": weather_tool.name,
            "gen_ai.tool.type": "function",
            **transfer_attributes,
        }
        with _reference_tracer.start_as_current_span(
            f"execute_tool {weather_tool.name} {specialist.name}", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.call.id", tool_context.tool_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", input_json)
            target_span_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.request.model": request_model,
                "gen_ai.agent.name": specialist.name,
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_agent {specialist.name}", attributes=target_span_attributes
            ) as target_span:
                result = await original_on_invoke_tool(tool_context, input_json)
                target_span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": str(result)}]}]),
                )
            tool_span.set_attribute("gen_ai.tool.call.result", str(result))
        return result

    caller = Agent(
        name="assistant",
        instructions="You are a helpful assistant. Delegate weather questions to the specialist.",
        model=model,
        tools=[weather_tool],
    )
    input_text = "What's the weather in Seattle?"

    print("  [delegation] agent-as-tool via Agent.as_tool (reference implementation)")
    # `_patched_method` installs the caller-owned execute_tool invoker and restores
    # it in `finally`. The caller's whole logical invocation is the public
    # `Runner.run(caller, ...)` call, so its execution span wraps that call directly
    # and owns the caller's input and response.
    caller_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": caller.name,
    }
    with (
        _patched_method(weather_tool, "on_invoke_tool", _traced_on_invoke_tool),
        _reference_tracer.start_as_current_span(
            f"invoke_agent {caller.name}", attributes=caller_span_attributes
        ) as caller_span,
    ):
        caller_span.set_attribute(
            "gen_ai.system_instructions", json.dumps([{"type": "text", "content": caller.instructions}])
        )
        caller_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )
        result = await Runner.run(caller, input_text)
        caller_span.set_attribute(
            "gen_ai.output.messages",
            json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": str(result.final_output)}]}]),
        )
    print(f"    -> {str(result.final_output)[:60]}")


async def run_command_execution():
    """Sandboxed command execution through the SDK's `exec_command` tool."""
    from agents.run_config import SandboxRunConfig
    from agents.sandbox import SandboxAgent
    from agents.sandbox.capabilities import Shell
    from agents.sandbox.capabilities.tools import ExecCommandTool
    from agents.sandbox.sandboxes import UnixLocalSandboxClient

    print("  [command] sandboxed command execution (reference implementation)")

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    class _TracedExecCommandTool(ExecCommandTool):
        """Records an `execute_tool` span around `ExecCommandTool`."""

        async def _invoke(self, ctx, raw_input):
            args = self.args_model.model_validate_json(raw_input)
            executable = args.shell
            executable_name = posixpath.basename(executable) if executable else None
            attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": self.name,
                "gen_ai.tool.type": "function",
            }
            if ctx.agent is not None and ctx.agent.name:
                attributes["gen_ai.agent.name"] = ctx.agent.name
            span_name = f"execute_tool {self.name}"
            if executable_name:
                attributes["process.executable.name"] = executable_name
                span_name = f"{span_name} {executable_name}"
            with _reference_tracer.start_as_current_span(span_name, attributes=attributes) as span:
                span.set_attribute("gen_ai.tool.description", self.description)
                span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
                span.set_attribute("gen_ai.tool.call.arguments", raw_input)
                if executable_name and posixpath.isabs(executable):
                    span.set_attribute("process.executable.path", executable)
                try:
                    result = await self.run(args)
                except Exception as exc:
                    span.set_attribute("error.type", type(exc).__qualname__)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise
                span.set_attribute("gen_ai.tool.call.result", result)
                return result

    sandbox_client = UnixLocalSandboxClient()
    session = await sandbox_client.create()
    await session.start()
    original_pty_exec_start = session.pty_exec_start

    async def _pty_exec_start(*command, **kwargs):
        update = await original_pty_exec_start(*command, **kwargs)
        if update.exit_code is not None:
            trace.get_current_span().set_attribute("process.exit.code", update.exit_code)
        return update

    session.pty_exec_start = _pty_exec_start

    allowed_command = ""

    def configure_tools(toolset):
        """Swap in the traced tool and narrow what the model may run."""
        toolset.exec_command = _TracedExecCommandTool(session=session)
        properties = toolset.exec_command.params_json_schema["properties"]
        properties["cmd"] = {**properties["cmd"], "enum": [allowed_command]}
        properties["shell"] = {
            "type": "string",
            "enum": [SANDBOX_SHELL],
            "description": properties["shell"]["description"],
        }
        toolset.exec_command.params_json_schema["required"] = ["cmd", "shell"]

    agent = SandboxAgent(
        name="command-agent",
        instructions="You run shell commands to answer questions about the workspace.",
        model=model,
        capabilities=[Shell(configure_tools=configure_tools)],
    )

    runs = (
        ("List the files in the workspace.", "ls -1a"),
        ("Show me the report.", "cat missing-report.txt"),
    )
    try:
        for input_text, command in runs:
            allowed_command = command
            result = await Runner.run(
                agent,
                input_text,
                run_config=RunConfig(sandbox=SandboxRunConfig(session=session)),
            )
            print(f"    -> {str(result.final_output)[:60]}")
    finally:
        await session.shutdown()


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


def main():
    print("=== Reference Implementation: OpenAI Agents Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent())
    asyncio.run(run_agent_as_tool_delegation())
    asyncio.run(run_command_execution())
    asyncio.run(run_workflow())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
