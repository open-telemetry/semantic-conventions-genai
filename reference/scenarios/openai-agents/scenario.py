"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling, agent-as-tool delegation, sandboxed
command execution, a multi-agent run with handoffs wrapped in an invoke_runner
span, and two-layer context propagation of gen_ai.agent.name onto openai
client inference metrics (including Responses usage and streaming).
"""

import asyncio
import json
import os
import posixpath
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from unittest.mock import patch

import openai
from agents import Agent, ModelSettings, RunConfig, Runner, function_tool
from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.run import AgentRunner
from agents.tool import FunctionTool, ToolContext
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import StatusCode
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
# The shell this deployment lets the sandboxed agent run commands with.
SANDBOX_SHELL = "/bin/bash"

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_AGENT_NAME_KEY = otel_context.create_key("gen_ai.agent.name")
_CLIENT_DURATION_BUCKETS = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60]

_inference_duration = _reference_meter.create_histogram(
    "gen_ai.client.inference.duration",
    unit="s",
    description="GenAI client inference operation duration.",
    explicit_bucket_boundaries_advisory=_CLIENT_DURATION_BUCKETS,
)
_time_to_first_chunk = _reference_meter.create_histogram(
    "gen_ai.client.inference.time_to_first_chunk",
    unit="s",
    description="Time to receive the first output chunk of a streaming inference operation.",
    explicit_bucket_boundaries_advisory=_CLIENT_DURATION_BUCKETS,
)
_time_per_output_chunk = _reference_meter.create_histogram(
    "gen_ai.client.inference.time_per_output_chunk",
    unit="s",
    description="Time between successive output chunks of a streaming inference operation.",
    explicit_bucket_boundaries_advisory=_CLIENT_DURATION_BUCKETS,
)
_operation_input_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used per inference operation.",
)
_operation_output_tokens = _reference_meter.create_histogram(
    "gen_ai.client.inference.operation.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used per inference operation.",
)
_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.input_tokens",
    unit="{token}",
    description="The number of input (prompt) tokens used, including cached tokens.",
)
_output_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.output_tokens",
    unit="{token}",
    description="The number of output (completion) tokens used, including reasoning tokens.",
)
_cache_read_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.cache_read.input_tokens",
    unit="{token}",
    description="The number of input tokens served from a provider-managed cache.",
)
_cache_write_input_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.cache_write.input_tokens",
    unit="{token}",
    description="The number of input tokens written to a provider-managed cache.",
)
_reasoning_output_tokens = _reference_meter.create_counter(
    "gen_ai.client.inference.usage.reasoning.output_tokens",
    unit="{token}",
    description="The number of output tokens used for reasoning.",
)


@contextmanager
def _agent_context(agent_name: str | None):
    """Propagate the name of the agent performing the operation in OTel context."""
    token = otel_context.attach(otel_context.set_value(_AGENT_NAME_KEY, agent_name or None))
    try:
        yield
    finally:
        otel_context.detach(token)


def _inference_metric_attributes(
    request_model: str,
    response_model: str | None,
    host: str | None,
    port: int | None,
    *,
    service_tier: str | None = None,
    agent_name: str | None = None,
) -> dict:
    attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if response_model:
        attributes["gen_ai.response.model"] = response_model
    if service_tier:
        attributes["gen_ai.response.service_tier"] = service_tier
    if agent_name:
        attributes["gen_ai.agent.name"] = agent_name
    if host:
        attributes["server.address"] = host
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _record_inference_metrics(duration: float, usage: dict[str, int], metric_attributes: dict) -> None:
    _inference_duration.record(duration, metric_attributes)
    input_tokens = usage.get("gen_ai.usage.input_tokens")
    if input_tokens is not None:
        _operation_input_tokens.record(input_tokens, metric_attributes)
        if input_tokens > 0:
            _input_tokens.add(input_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
    output_tokens = usage.get("gen_ai.usage.output_tokens")
    if output_tokens is not None:
        _operation_output_tokens.record(output_tokens, metric_attributes)
        if output_tokens > 0:
            _output_tokens.add(output_tokens, {**metric_attributes, "gen_ai.token.modality": "unknown"})
    for attr, counter in (
        ("gen_ai.usage.cache_read.input_tokens", _cache_read_input_tokens),
        ("gen_ai.usage.cache_write.input_tokens", _cache_write_input_tokens),
    ):
        value = usage.get(attr)
        if value is not None and value > 0:
            counter.add(value, {**metric_attributes, "gen_ai.token.modality": "unknown"})
    reasoning_tokens = usage.get("gen_ai.usage.reasoning.output_tokens")
    if reasoning_tokens is not None and reasoning_tokens > 0:
        _reasoning_output_tokens.add(reasoning_tokens, metric_attributes)


def _extract_chat_usage(usage) -> dict[str, int]:
    if usage is None:
        return {}
    result: dict[str, int] = {
        "gen_ai.usage.input_tokens": usage.prompt_tokens,
        "gen_ai.usage.output_tokens": usage.completion_tokens,
    }
    prompt_details = usage.prompt_tokens_details
    if prompt_details is not None:
        if prompt_details.cached_tokens:
            result["gen_ai.usage.cache_read.input_tokens"] = prompt_details.cached_tokens
        if prompt_details.cache_write_tokens:
            result["gen_ai.usage.cache_write.input_tokens"] = prompt_details.cache_write_tokens
    completion_details = usage.completion_tokens_details
    if completion_details is not None and completion_details.reasoning_tokens:
        result["gen_ai.usage.reasoning.output_tokens"] = completion_details.reasoning_tokens
    return result


def _extract_responses_usage(usage) -> dict[str, int]:
    if usage is None:
        return {}
    result: dict[str, int] = {
        "gen_ai.usage.input_tokens": usage.input_tokens,
        "gen_ai.usage.output_tokens": usage.output_tokens,
    }
    input_details = usage.input_tokens_details
    if input_details is not None:
        if input_details.cached_tokens:
            result["gen_ai.usage.cache_read.input_tokens"] = input_details.cached_tokens
        if input_details.cache_write_tokens:
            result["gen_ai.usage.cache_write.input_tokens"] = input_details.cache_write_tokens
    output_details = usage.output_tokens_details
    if output_details is not None and output_details.reasoning_tokens:
        result["gen_ai.usage.reasoning.output_tokens"] = output_details.reasoning_tokens
    return result


class _ObservedAsyncChatStream:
    """Client-layer wrapper recording streaming inference metrics with the agent name from context."""

    def __init__(
        self,
        stream,
        *,
        request_model: str,
        host: str | None,
        port: int | None,
        agent_name: str | None,
        started_at: float,
        recorded_agents: list[str | None],
    ):
        self._stream = stream
        self._request_model = request_model
        self._host = host
        self._port = port
        self._agent_name = agent_name
        self._started_at = started_at
        self._recorded_agents = recorded_agents
        self._response_model: str | None = None
        self._service_tier: str | None = None
        self._usage: dict[str, int] = {}
        self._previous_output_at: float | None = None
        self._finished = False

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = await self._stream.__anext__()
        except StopAsyncIteration:
            self._finalize()
            raise
        received_at = perf_counter()
        self._response_model = self._response_model or chunk.model
        self._service_tier = self._service_tier or chunk.service_tier
        has_output = any(
            choice.delta.content
            or choice.delta.refusal
            or any(
                call.function and (call.function.name or call.function.arguments)
                for call in choice.delta.tool_calls or []
            )
            for choice in chunk.choices
        )
        if has_output:
            chunk_attributes = _inference_metric_attributes(
                self._request_model,
                self._response_model,
                self._host,
                self._port,
                service_tier=self._service_tier,
                agent_name=self._agent_name,
            )
            assert chunk_attributes.get("gen_ai.agent.name") == self._agent_name
            if self._previous_output_at is None:
                _time_to_first_chunk.record(received_at - self._started_at, chunk_attributes)
            else:
                _time_per_output_chunk.record(received_at - self._previous_output_at, chunk_attributes)
            self._previous_output_at = received_at
        if chunk.usage:
            self._usage = _extract_chat_usage(chunk.usage)
        return chunk

    def _finalize(self) -> None:
        if self._finished:
            return
        self._finished = True
        metric_attributes = _inference_metric_attributes(
            self._request_model,
            self._response_model,
            self._host,
            self._port,
            service_tier=self._service_tier,
            agent_name=self._agent_name,
        )
        self._recorded_agents.append(metric_attributes.get("gen_ai.agent.name"))
        _record_inference_metrics(perf_counter() - self._started_at, self._usage, metric_attributes)


def _instrument_openai_client(client: openai.AsyncOpenAI) -> list[str | None]:
    """Simulate in-process openai client metric instrumentation reading gen_ai.agent.name from context."""
    host, port = mock_server_host_port(str(client.base_url))
    recorded_agents: list[str | None] = []

    original_chat_create = client.chat.completions.create

    async def _metered_chat_create(*args, **kwargs):
        agent_name = otel_context.get_value(_AGENT_NAME_KEY)
        request_model = kwargs["model"]
        started_at = perf_counter()
        response = await original_chat_create(*args, **kwargs)
        if kwargs.get("stream"):
            return _ObservedAsyncChatStream(
                response,
                request_model=request_model,
                host=host,
                port=port,
                agent_name=agent_name,
                started_at=started_at,
                recorded_agents=recorded_agents,
            )
        metric_attributes = _inference_metric_attributes(
            request_model,
            response.model,
            host,
            port,
            service_tier=response.service_tier,
            agent_name=agent_name,
        )
        recorded_agents.append(metric_attributes.get("gen_ai.agent.name"))
        _record_inference_metrics(perf_counter() - started_at, _extract_chat_usage(response.usage), metric_attributes)
        return response

    client.chat.completions.create = _metered_chat_create

    original_responses_create = client.responses.create

    async def _metered_responses_create(*args, **kwargs):
        agent_name = otel_context.get_value(_AGENT_NAME_KEY)
        request_model = kwargs["model"]
        started_at = perf_counter()
        response = await original_responses_create(*args, **kwargs)
        metric_attributes = _inference_metric_attributes(
            request_model,
            response.model,
            host,
            port,
            service_tier=response.service_tier,
            agent_name=agent_name,
        )
        recorded_agents.append(metric_attributes.get("gen_ai.agent.name"))
        _record_inference_metrics(
            perf_counter() - started_at, _extract_responses_usage(response.usage), metric_attributes
        )
        return response

    client.responses.create = _metered_responses_create
    return recorded_agents


def instrument_function_tool(tool: FunctionTool) -> FunctionTool:
    original_on_invoke_tool = tool.on_invoke_tool

    async def traced_on_invoke_tool(ctx, input_json):
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool.name,
            "gen_ai.tool.type": "function",
        }
        if ctx.agent is not None and ctx.agent.name:
            tool_span_attributes["gen_ai.agent.name"] = ctx.agent.name
        with _reference_tracer.start_as_current_span(
            f"execute_tool {tool.name}", attributes=tool_span_attributes, record_exception=False
        ) as tool_span:
            try:
                tool_span.set_attribute("gen_ai.tool.description", tool.description)
                if ctx.tool_call_id:
                    tool_span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.loads(input_json or "{}"))
                result = await original_on_invoke_tool(ctx, input_json)
                # TODO: Determine how to represent this string result in the object-only schema.
                tool_span.set_attribute("gen_ai.tool.call.result", result)
                return result
            except Exception as e:
                tool_span.set_status(StatusCode.ERROR, str(e))
                tool_span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
                reference_event_logger().emit(
                    event_name="gen_ai.execute_tool.exception",
                    severity_number=SeverityNumber.WARN,
                    exception=e,
                )
                raise

    tool.on_invoke_tool = traced_on_invoke_tool
    return tool


@instrument_function_tool
@function_tool
def get_weather(ctx: ToolContext[None], location: str) -> str:
    """Get the current weather for a location."""
    return "Sunny, 72°F"


async def _emit_agent_span(client, agent, input_text, *, stream: bool = False, **run_kwargs):
    captured_responses = []
    agent_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.request.model": agent.model.model,
        "gen_ai.agent.name": agent.name,
    }
    with (
        _reference_tracer.start_as_current_span(
            f"invoke_agent {agent.name}", attributes=agent_span_attributes, record_exception=False
        ) as agent_span,
        _agent_context(agent.name),
    ):
        try:
            if agent.instructions:
                agent_span.set_attribute(
                    "gen_ai.system_instructions", [{"type": "text", "content": agent.instructions}]
                )
            agent_span.set_attribute(
                "gen_ai.input.messages",
                [{"role": "user", "parts": [{"type": "text", "content": input_text}]}],
            )
            if agent.tools:
                agent_span.set_attribute(
                    "gen_ai.tool.definitions",
                    [
                        {
                            "type": "function",
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.params_json_schema,
                        }
                        for t in agent.tools
                        if isinstance(t, FunctionTool)
                    ],
                )
            if stream:
                result = Runner.run_streamed(agent, input_text, **run_kwargs)
                async for _ in result.stream_events():
                    pass
            else:
                original_create = client.chat.completions.create

                async def _capture_create(*args, **kwargs):
                    response = await original_create(*args, **kwargs)
                    captured_responses.append(response)
                    return response

                client.chat.completions.create = _capture_create
                try:
                    result = await Runner.run(agent, input_text, **run_kwargs)
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
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": str(result.final_output)}],
                        }
                    ],
                )
            print(f"    -> {str(result.final_output)[:60]}")
        except Exception as e:
            agent_span.set_status(StatusCode.ERROR, str(e))
            agent_span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
            reference_event_logger().emit(
                event_name="gen_ai.invoke_agent.exception",
                severity_number=SeverityNumber.WARN,
                exception=e,
            )
            raise
    return result


async def run_agent():
    """Run a simple agent with the OpenAI Agents SDK, with manual spans."""
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    recorded_agents = _instrument_openai_client(client)
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)

    tools = [get_weather]
    agent = Agent(
        name="test-agent",
        instructions="You are a helpful assistant.",
        model=model,
        tools=tools,
    )
    input_text = "What's the weather in Seattle?"

    print("  [agent_run] agent with tool calling (reference implementation)")
    await _emit_agent_span(client, agent, input_text)
    assert recorded_agents and set(recorded_agents) == {"test-agent"}, recorded_agents


async def run_tool_error_reference():
    """Exercise an SDK tool-argument validation exception."""

    @instrument_function_tool
    @function_tool(failure_error_function=None)
    def get_weather(location: str) -> str:
        """Get the current weather for a location."""
        return f"Sunny in {location}"

    input_json = '{"location": 42}'
    tool_context = ToolContext(
        context=None,
        tool_name=get_weather.name,
        tool_call_id="",
        tool_arguments=input_json,
    )
    print("  [tool_error] SDK tool-argument validation (reference implementation)")
    try:
        await get_weather.on_invoke_tool(tool_context, input_json)
    except ModelBehaviorError:
        pass
    else:
        raise AssertionError("Expected the SDK to reject the tool arguments")


async def run_agent_error_reference():
    """Exercise the SDK's agent turn-limit exception."""
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    model = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
    agent = Agent(name="turn-limit-agent", model=model)

    print("  [agent_error] SDK agent turn limit (reference implementation)")
    try:
        await _emit_agent_span(client, agent, "Hello", max_turns=0)
    except MaxTurnsExceeded:
        pass
    else:
        raise AssertionError("Expected the SDK to enforce the agent turn limit")


async def run_agent_as_tool_delegation():
    """Delegation: a caller agent invokes another agent exposed via `Agent.as_tool`.

    `Agent.as_tool()` runs the target agent as a function tool and returns its
    result to the original agent. The caller-owned `execute_tool` span records
    the transfer; the child `invoke_agent` span records the target's execution.
    """
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    recorded_agents = _instrument_openai_client(client)
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

    original_on_invoke_tool = weather_tool.on_invoke_tool

    async def _traced_on_invoke_tool(tool_context, input_json):
        transfer_attributes = {
            "gen_ai.agent.name": tool_context.agent.name,
            "gen_ai.transfer.mode": "return_to_caller",
            "gen_ai.transfer.target.name": weather_tool._agent_instance.name,
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
            f"execute_tool {weather_tool.name}", attributes=tool_span_attributes, record_exception=False
        ) as tool_span:
            try:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_context.tool_call_id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.loads(input_json or "{}"))
                result = await original_on_invoke_tool(tool_context, input_json)
                # TODO: Determine how to represent this string result in the object-only schema.
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            except Exception as e:
                tool_span.set_status(StatusCode.ERROR, str(e))
                tool_span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
                reference_event_logger().emit(
                    event_name="gen_ai.execute_tool.exception",
                    severity_number=SeverityNumber.WARN,
                    exception=e,
                )
                raise
        return result

    model_responses = ContextVar("delegation_model_responses", default=None)
    original_create = client.chat.completions.create
    original_agent_run = AgentRunner.run

    async def _capture_create(*args, **kwargs):
        response = await original_create(*args, **kwargs)
        responses = model_responses.get()
        if responses is not None:
            responses.append(response)
        return response

    async def _traced_agent_run(runner, starting_agent, input, **kwargs):
        agent_span_attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.request.model": starting_agent.model.model,
            "gen_ai.agent.name": starting_agent.name,
        }
        with (
            _reference_tracer.start_as_current_span(
                f"invoke_agent {starting_agent.name}", attributes=agent_span_attributes, record_exception=False
            ) as agent_span,
            _agent_context(starting_agent.name),
        ):
            try:
                agent_span.set_attribute(
                    "gen_ai.system_instructions", [{"type": "text", "content": starting_agent.instructions}]
                )
                agent_span.set_attribute(
                    "gen_ai.input.messages",
                    [{"role": "user", "parts": [{"type": "text", "content": input}]}],
                )
                responses = []
                token = model_responses.set(responses)
                try:
                    result = await original_agent_run(runner, starting_agent, input, **kwargs)
                finally:
                    model_responses.reset(token)
                # Agent.as_tool shares context usage with its caller. Each run's raw
                # responses identify its own model usage without counting the other agent.
                if result.raw_responses:
                    agent_span.set_attribute(
                        "gen_ai.usage.input_tokens",
                        sum(response.usage.input_tokens for response in result.raw_responses),
                    )
                    agent_span.set_attribute(
                        "gen_ai.usage.output_tokens",
                        sum(response.usage.output_tokens for response in result.raw_responses),
                    )
                finish_reasons = []
                if responses:
                    finish_reasons = [
                        choice.finish_reason for choice in responses[-1].choices if choice.finish_reason is not None
                    ]
                    if finish_reasons:
                        agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
                output_message = {
                    "role": "assistant",
                    "parts": [{"type": "text", "content": str(result.final_output)}],
                }
                if len(finish_reasons) == 1:
                    output_message["finish_reason"] = finish_reasons[0]
                agent_span.set_attribute("gen_ai.output.messages", [output_message])
            except Exception as e:
                agent_span.set_status(StatusCode.ERROR, str(e))
                agent_span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
                reference_event_logger().emit(
                    event_name="gen_ai.invoke_agent.exception",
                    severity_number=SeverityNumber.WARN,
                    exception=e,
                )
                raise
        return result

    caller = Agent(
        name="assistant",
        instructions="You are a helpful assistant. Delegate weather questions to the specialist.",
        model=model,
        tools=[weather_tool],
    )
    input_text = "What's the weather in Seattle?"

    print("  [delegation] agent-as-tool via Agent.as_tool (reference implementation)")
    with (
        patch.object(weather_tool, "on_invoke_tool", _traced_on_invoke_tool),
        patch.object(AgentRunner, "run", _traced_agent_run),
        patch.object(client.chat.completions, "create", _capture_create),
    ):
        result = await Runner.run(caller, input_text)
    assert recorded_agents == ["assistant", "weather-specialist", "assistant"], recorded_agents
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
    recorded_agents = _instrument_openai_client(client)
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
            with _reference_tracer.start_as_current_span(
                span_name, attributes=attributes, record_exception=False
            ) as span:
                try:
                    span.set_attribute("gen_ai.tool.description", self.description)
                    span.set_attribute("gen_ai.tool.call.id", ctx.tool_call_id)
                    span.set_attribute("gen_ai.tool.call.arguments", json.loads(raw_input))
                    if executable_name and posixpath.isabs(executable):
                        span.set_attribute("process.executable.path", executable)
                    result = await self.run(args)
                    # TODO: Determine how to represent this string result in the object-only schema.
                    span.set_attribute("gen_ai.tool.call.result", result)
                    return result
                except Exception as exc:
                    span.set_attribute("error.type", f"{type(exc).__module__}.{type(exc).__qualname__}")
                    span.set_status(StatusCode.ERROR, str(exc))
                    reference_event_logger().emit(
                        event_name="gen_ai.execute_tool.exception",
                        severity_number=SeverityNumber.WARN,
                        exception=exc,
                    )
                    raise

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
            with _agent_context(agent.name):
                result = await Runner.run(
                    agent,
                    input_text,
                    run_config=RunConfig(sandbox=SandboxRunConfig(session=session)),
                )
            print(f"    -> {str(result.final_output)[:60]}")
        assert recorded_agents and set(recorded_agents) == {"command-agent"}, recorded_agents
    finally:
        await session.shutdown()


async def run_runner():
    """Run a multi-agent handoff wrapped in an `invoke_runner` span for the `Runner.run` call."""
    from agents import handoff
    from agents import run as agent_run
    from agents.run_internal import turn_resolution

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    recorded_agents = _instrument_openai_client(client)
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

    original_execute_handoffs = turn_resolution.execute_handoffs
    original_run_single_turn = agent_run.run_single_turn
    original_create = client.chat.completions.create

    async def traced_execute_handoffs(*, public_agent, run_handoffs, **kwargs):
        # The SDK executes only the first handoff when a model requests several.
        selected = run_handoffs[0]
        original_invoke = selected.handoff.on_invoke_handoff

        async def traced_invoke(context, arguments):
            attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": selected.tool_call.name,
                "gen_ai.tool.type": "function",
                "gen_ai.agent.name": public_agent.name,
            }
            with _reference_tracer.start_as_current_span(
                f"execute_tool {selected.tool_call.name}", attributes=attributes, record_exception=False
            ) as span:
                try:
                    span.set_attribute("gen_ai.tool.call.id", selected.tool_call.call_id)
                    span.set_attribute("gen_ai.tool.call.arguments", json.loads(arguments or "{}"))
                    target = await original_invoke(context, arguments)
                    span.set_attribute("gen_ai.transfer.mode", "pass_control")
                    span.set_attribute("gen_ai.transfer.target.name", target.name)
                    span.set_attribute(
                        "gen_ai.tool.call.result", json.loads(selected.handoff.get_transfer_message(target))
                    )
                    return target
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
                    reference_event_logger().emit(
                        event_name="gen_ai.execute_tool.exception",
                        severity_number=SeverityNumber.WARN,
                        exception=e,
                    )
                    raise

        with patch.object(selected.handoff, "on_invoke_handoff", traced_invoke):
            return await original_execute_handoffs(public_agent=public_agent, run_handoffs=run_handoffs, **kwargs)

    async def traced_run_single_turn(*, bindings, **kwargs):
        agent = bindings.public_agent
        attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": agent.name,
            "gen_ai.request.model": agent.model.model,
        }
        with (
            _reference_tracer.start_as_current_span(
                f"invoke_agent {agent.name}", attributes=attributes, record_exception=False
            ) as span,
            _agent_context(agent.name),
        ):
            try:
                result = await original_run_single_turn(bindings=bindings, **kwargs)
                span.set_attribute("gen_ai.usage.input_tokens", result.model_response.usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", result.model_response.usage.output_tokens)
                parts = []
                for item in result.model_response.output:
                    if item.type == "message":
                        parts.extend(
                            {"type": "text", "content": content.text}
                            for content in item.content
                            if content.type == "output_text"
                        )
                    elif item.type == "function_call":
                        parts.append(
                            {
                                "type": "tool_call",
                                "id": item.call_id,
                                "name": item.name,
                                "arguments": json.loads(item.arguments or "{}"),
                            }
                        )
                if parts:
                    span.set_attribute("gen_ai.output.messages", [{"role": "assistant", "parts": parts}])
                return result
            except Exception as e:
                span.set_status(StatusCode.ERROR, str(e))
                span.set_attribute("error.type", f"{type(e).__module__}.{type(e).__qualname__}")
                reference_event_logger().emit(
                    event_name="gen_ai.invoke_agent.exception",
                    severity_number=SeverityNumber.WARN,
                    exception=e,
                )
                raise

    async def capture_create(*args, **kwargs):
        response = await original_create(*args, **kwargs)
        finish_reasons = [choice.finish_reason for choice in response.choices if choice.finish_reason is not None]
        if finish_reasons:
            trace.get_current_span().set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        return response

    print("  [runner_run] multi-agent handoff via Runner.run (reference implementation)")
    # `Runner` is not itself an agent or a workflow, so its invocation is `invoke_runner`.
    runner_span_attributes = {
        "gen_ai.operation.name": "invoke_runner",
    }
    with _reference_tracer.start_as_current_span("invoke_runner", attributes=runner_span_attributes) as runner_span:
        runner_span.set_attribute(
            "gen_ai.input.messages", [{"role": "user", "parts": [{"type": "text", "content": input_text}]}]
        )

        with (
            patch.object(turn_resolution, "execute_handoffs", traced_execute_handoffs),
            patch.object(agent_run, "run_single_turn", traced_run_single_turn),
            patch.object(client.chat.completions, "create", capture_create),
        ):
            result = await Runner.run(agent_a, input_text)
        assert recorded_agents == ["agent-a", "agent-b"], recorded_agents

        if result.final_output:
            output_messages = [
                {
                    "role": "assistant",
                    "parts": [{"type": "text", "content": str(result.final_output)}],
                }
            ]
            runner_span.set_attribute("gen_ai.output.messages", output_messages)
        print(f"    -> {str(result.final_output)[:60]}")


async def run_agent_responses_and_streaming():
    """Exercise Responses API token usage and streamed chat completions under agent context."""
    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    recorded_agents = _instrument_openai_client(client)
    request_model = "gpt-4o-mini"

    responses_agent = Agent(
        name="responses-agent",
        instructions="You are a concise assistant.",
        model=OpenAIResponsesModel(model=request_model, openai_client=client),
    )
    print("  [responses] agent Responses API usage (reference implementation)")
    await _emit_agent_span(client, responses_agent, "Summarize the conversation so far.")

    streaming_agent = Agent(
        name="streaming-agent",
        instructions="You are a helpful assistant.",
        model=OpenAIChatCompletionsModel(model=request_model, openai_client=client),
        model_settings=ModelSettings(include_usage=True),
    )
    print("  [streaming] streamed agent run (reference implementation)")
    await _emit_agent_span(client, streaming_agent, "Say hello in a short sentence.", stream=True)
    assert recorded_agents == ["responses-agent", "streaming-agent"], recorded_agents


def main():
    print("=== Reference Implementation: OpenAI Agents Reference Implementation ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent())
    asyncio.run(run_tool_error_reference())
    asyncio.run(run_agent_error_reference())
    asyncio.run(run_agent_as_tool_delegation())
    asyncio.run(run_command_execution())
    asyncio.run(run_runner())
    asyncio.run(run_agent_responses_and_streaming())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
