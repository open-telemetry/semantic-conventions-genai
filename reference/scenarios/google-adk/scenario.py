"""Reference implementation for Google ADK."""

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from opentelemetry import trace as _trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

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


class SpanCounter(SpanProcessor):
    """Lightweight span counter for diagnosing whether instrumentation fires."""

    def __init__(self):
        self.count = 0

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        self.count += 1

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True


class A2ATopologyRecorder(SpanProcessor):
    """Verify the remote-agent CLIENT span is nested under its ADK agent run."""

    def __init__(self):
        self.internal_span_id = None
        self.client_parent_span_id = None

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span: ReadableSpan):
        attributes = span.attributes or {}
        if attributes.get("gen_ai.operation.name") != "invoke_agent":
            return
        if span.kind == SpanKind.INTERNAL and attributes.get("gen_ai.agent.name") == "remote_weather_agent":
            self.internal_span_id = span.context.span_id
        elif span.kind == SpanKind.CLIENT and attributes.get("gen_ai.agent.name") == "weather-agent":
            self.client_parent_span_id = span.parent.span_id if span.parent else None

    def assert_valid(self):
        if self.internal_span_id is None:
            raise AssertionError("RemoteA2aAgent INTERNAL span was not recorded")
        if self.client_parent_span_id != self.internal_span_id:
            raise AssertionError("A2A CLIENT span is not a child of the RemoteA2aAgent INTERNAL span")

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True


@contextlib.contextmanager
def _run_a2a_server():
    host = "127.0.0.1"
    with socket.socket() as sock:
        sock.bind((host, 0))
        port = sock.getsockname()[1]

    server_path = Path(__file__).with_name("a2a_server.py")
    process = subprocess.Popen(
        [sys.executable, str(server_path), "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://{host}:{port}"
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"A2A server exited with code {process.returncode}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("A2A server did not become ready")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@contextlib.contextmanager
def _suppress_adk_native_telemetry():
    from google.adk import runners as adk_runners
    from google.adk.agents import base_agent as adk_base_agent
    from google.adk.flows.llm_flows import base_llm_flow as adk_base_llm_flow
    from google.adk.flows.llm_flows import functions as adk_functions
    from google.adk.telemetry import _metrics as adk_metrics
    from google.adk.telemetry import tracing as adk_tracing

    class _DisabledTracer:
        @contextlib.contextmanager
        def start_as_current_span(self, *_args, **_kwargs):
            yield _trace.NonRecordingSpan(_trace.INVALID_SPAN_CONTEXT)

    class _DisabledInstrument:
        def record(self, *_args, **_kwargs):
            pass

    disabled_tracer = _DisabledTracer()
    disabled_instrument = _DisabledInstrument()
    patched_modules = (
        adk_tracing,
        adk_base_agent,
        adk_runners,
        adk_base_llm_flow,
        adk_functions,
    )
    previous_attributes = []

    def patch_attribute(owner, name, value):
        if hasattr(owner, name):
            previous_attributes.append((owner, name, getattr(owner, name)))
            setattr(owner, name, value)

    try:
        for module in patched_modules:
            patch_attribute(module, "tracer", disabled_tracer)
        patch_attribute(adk_tracing.otel_logger, "emit", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_call_llm", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_tool_call", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_merged_tool_calls", lambda *_args, **_kwargs: None)
        patch_attribute(adk_base_llm_flow, "trace_call_llm", lambda *_args, **_kwargs: None)
        patch_attribute(adk_functions, "trace_tool_call", lambda *_args, **_kwargs: None)
        patch_attribute(adk_functions, "trace_merged_tool_calls", lambda *_args, **_kwargs: None)
        # ADK records gen_ai.client.token.usage and gen_ai.client.operation.duration for the model
        # call it hands to google-genai, but only as a fallback for when no model-client
        # instrumentation is loaded (see tracing._should_emit_native_telemetry). That call belongs
        # to google-genai, so drop those two instruments. Every other ADK instrument is left alone,
        # including the invoke_agent inference/tool call counts, which describe ADK's own work.
        patch_attribute(adk_metrics, "_client_operation_duration", disabled_instrument)
        patch_attribute(adk_metrics, "_client_token_usage", disabled_instrument)
        yield
    finally:
        for owner, name, value in reversed(previous_attributes):
            setattr(owner, name, value)


def run_agent_reference():
    """Scenario: basic agent execution via Google ADK with reference implementation."""
    from google.adk.agents import Agent
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types

    print("  [agent_run] basic ADK agent execution (reference implementation)")

    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")
    request_model = "gemini-2.0-flash"
    input_text = "Say hello."
    request_choice_count = 2
    request_temperature = 0.25
    request_top_p = 0.8
    request_top_k = 5
    request_max_tokens = 96
    request_stop_sequences = ["<END>"]
    request_presence_penalty = 0.4
    request_frequency_penalty = 0.2

    # Per-invocation call counts, scoped to the single agent invocation below.
    # ADK can attribute each inference/tool call to the agent that issued it,
    # which is exactly the criteria the invoke_agent call-count metrics require.
    call_counts = {"inference": 0, "tool": 0}

    def get_weather(location: str, tool_context: ToolContext) -> str:
        """Get the current weather."""
        call_counts["tool"] += 1
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "get_weather",
            "gen_ai.tool.type": "function",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.description", "Get the current weather.")
            tool_span.set_attribute("gen_ai.agent.name", tool_context.agent_name)
            if tool_context.function_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_context.function_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = f"Sunny in {location}"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
        return result

    tool_defs = [
        {
            "name": "get_weather",
            "description": "Get the current weather.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "location": {"type": "STRING", "description": "City name"},
                },
                "required": ["location"],
            },
        }
    ]

    with _suppress_adk_native_telemetry():
        agent = Agent(
            name="test_agent",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You are a helpful assistant.",
            tools=[get_weather],
            generate_content_config=types.GenerateContentConfig(
                candidate_count=request_choice_count,
                temperature=request_temperature,
                top_p=request_top_p,
                top_k=request_top_k,
                max_output_tokens=request_max_tokens,
                stop_sequences=request_stop_sequences,
                presence_penalty=request_presence_penalty,
                frequency_penalty=request_frequency_penalty,
            ),
        )

        session_service = InMemorySessionService()
        runner = Runner(agent=agent, app_name="test_app", session_service=session_service)

        async def _run():
            session = await session_service.create_session(
                app_name="test_app",
                user_id="test_user",
            )
            workflow_span_attributes = {
                "gen_ai.operation.name": "invoke_workflow",
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_workflow {runner.app_name}", attributes=workflow_span_attributes
            ) as workflow_span:
                workflow_span.set_attribute("gen_ai.workflow.name", runner.app_name)
                workflow_span.set_attribute("gen_ai.conversation.id", session.id)
                workflow_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                agent_span_attributes = {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.request.model": request_model,
                    "gen_ai.agent.name": agent.name,
                }
                with _reference_tracer.start_as_current_span(
                    "invoke_agent test_agent", attributes=agent_span_attributes
                ) as agent_span:
                    agent_span.set_attribute("gen_ai.request.choice.count", request_choice_count)
                    agent_span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
                    agent_span.set_attribute("gen_ai.request.temperature", request_temperature)
                    agent_span.set_attribute("gen_ai.request.top_p", request_top_p)
                    agent_span.set_attribute("gen_ai.request.top_k", request_top_k)
                    agent_span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                    agent_span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                    agent_span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                    agent_span.set_attribute("gen_ai.conversation.id", session.id)
                    agent_span.set_attribute(
                        "gen_ai.system_instructions",
                        json.dumps([{"type": "text", "content": agent.instruction}]),
                    )
                    agent_span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                    )
                    agent_span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
                    usage_metadata = None
                    finish_reason = None
                    last_text = ""
                    async for event in runner.run_async(
                        user_id="test_user",
                        session_id=session.id,
                        new_message=types.Content(
                            role="user",
                            parts=[types.Part(text=input_text)],
                        ),
                    ):
                        if getattr(event, "usage_metadata", None) is not None:
                            # Only model-response events carry usage, so this counts
                            # one inference call per LLM round-trip.
                            call_counts["inference"] += 1
                            usage_metadata = event.usage_metadata
                        event_finish_reason = getattr(event, "finish_reason", None)
                        if isinstance(event, dict):
                            event_finish_reason = event.get("finish_reason")
                        if event_finish_reason is not None:
                            finish_reason = getattr(event_finish_reason, "value", event_finish_reason)
                        if event.content and event.content.parts:
                            text = event.content.parts[0].text
                            if text:
                                last_text = text
                                print(f"    -> {text[:60]}")
                    if usage_metadata is not None:
                        prompt_token_count = getattr(usage_metadata, "prompt_token_count", None)
                        candidate_token_count = getattr(usage_metadata, "candidates_token_count", None)
                        if isinstance(usage_metadata, dict):
                            prompt_token_count = usage_metadata.get("prompt_token_count")
                            candidate_token_count = usage_metadata.get("candidates_token_count")
                        if prompt_token_count is not None:
                            agent_span.set_attribute("gen_ai.usage.input_tokens", prompt_token_count)
                        if candidate_token_count is not None:
                            agent_span.set_attribute("gen_ai.usage.output_tokens", candidate_token_count)
                    if finish_reason is not None:
                        agent_span.set_attribute(
                            "gen_ai.response.finish_reasons",
                            [str(finish_reason).lower()],
                        )
                    if last_text:
                        output_messages = json.dumps(
                            [
                                {
                                    "role": "assistant",
                                    "parts": [{"type": "text", "content": last_text}],
                                }
                            ]
                        )
                        agent_span.set_attribute("gen_ai.output.messages", output_messages)
                        workflow_span.set_attribute("gen_ai.output.messages", output_messages)

        asyncio.run(_run())

        # Both metrics are scoped to the agent invocation and emitted alongside
        # the invoke_agent (internal) span, dimensioned by the agent name.
        metric_attributes = {"gen_ai.agent.name": agent.name}
        _inference_calls.record(call_counts["inference"], metric_attributes)
        _tool_calls.record(call_counts["tool"], metric_attributes)


def run_memory_reference():
    """Scenario: Google ADK memory add/search with reference implementation."""
    from google.adk.events.event import Event
    from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
    from google.adk.sessions.session import Session
    from google.genai import types

    print("  [memory] ADK in-memory memory service (reference implementation)")

    app_name = "test_app"
    user_id = "test_user"
    session_id = "session_memory_1"
    # `derivable`: ADK's InMemoryMemoryService keys its internal store on
    # (app_name, user_id), so this tuple is the library's own scope unit
    # for memory storage and retrieval.
    store_id = f"{app_name}/{user_id}"
    memory_text = "User prefers vegetarian meals and dark mode."
    query_text = "vegetarian meals"

    async def _run():
        # ADK's InMemoryMemoryService has no public store-lifecycle API and
        # produces no store identifier at construction, so create_memory_store
        # is an honest capture gap for this library. The operation is covered
        # by reference/scenarios/aws-bedrock-agentcore/ where the returned
        # memoryId is captured directly.
        memory_service = InMemoryMemoryService()

        event = Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text=memory_text)]),
        )
        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            events=[event],
        )
        memory_records = json.dumps(
            [
                {
                    "content": memory_text,
                    "id": event.id,
                    "metadata": {"author": event.author, "session_id": session.id},
                }
            ]
        )

        upsert_span_attributes = {
            "gen_ai.operation.name": "upsert_memory",
            "gen_ai.memory.store.id": store_id,
        }
        with _reference_tracer.start_as_current_span("upsert_memory", attributes=upsert_span_attributes) as upsert_span:
            upsert_span.set_attribute("gen_ai.memory.record.count", len(session.events))
            upsert_span.set_attribute("gen_ai.memory.records", memory_records)
            await memory_service.add_session_to_memory(session)

        search_span_attributes = {
            "gen_ai.operation.name": "search_memory",
            "gen_ai.memory.store.id": store_id,
        }
        with _reference_tracer.start_as_current_span("search_memory", attributes=search_span_attributes) as search_span:
            search_span.set_attribute("gen_ai.memory.query.text", query_text)
            response = await memory_service.search_memory(
                app_name=app_name,
                user_id=user_id,
                query=query_text,
            )
            search_records = []
            for memory in response.memories:
                content_text = " ".join(part.text for part in memory.content.parts if part.text)
                search_record = {
                    "content": content_text,
                    "metadata": {"author": memory.author},
                }
                if memory.id:
                    search_record["id"] = memory.id
                search_records.append(search_record)
            search_span.set_attribute("gen_ai.memory.record.count", len(search_records))
            search_span.set_attribute("gen_ai.memory.records", json.dumps(search_records))

    asyncio.run(_run())


def run_multi_agent_delegation_reference():
    """Delegation: a caller agent invokes a sub-agent exposed via ``AgentTool``.

    ``AgentTool`` runs the wrapped agent and returns its result to the caller.
    The caller-owned ``execute_tool`` span records the transfer; the child
    ``invoke_agent`` span records the target's execution.
    """
    from google.adk.agents import Agent
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.agent_tool import AgentTool
    from google.genai import types

    print("  [delegation] agent-as-tool via AgentTool (reference implementation)")

    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")
    request_model = "gemini-2.0-flash"
    input_text = "What's the weather in Seattle?"

    with _suppress_adk_native_telemetry():
        # The target sub-agent has no tools, so its mock model call returns text.
        specialist = Agent(
            name="weather_specialist",
            description="Answers weather questions for a given location.",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You report the weather.",
        )
        agent_tool = AgentTool(agent=specialist)

        # Wrap the tool's public run_async to open the caller-owned execute_tool
        # span around the real sub-agent invocation. The entry point stays
        # runner.run_async; the patched method is installed and restored in
        # `finally` by `_patched_method` below.
        original_run_async = agent_tool.run_async

        async def _traced_run_async(*, args, tool_context):
            transfer_attributes = {
                "gen_ai.agent.name": root_agent.name,
                "gen_ai.transfer.mode": "return_to_caller",
                "gen_ai.transfer.target.name": specialist.name,
                "gen_ai.transfer.target.type": "agent",
            }
            assert transfer_attributes == {
                "gen_ai.agent.name": "root_agent",
                "gen_ai.transfer.mode": "return_to_caller",
                "gen_ai.transfer.target.name": "weather_specialist",
                "gen_ai.transfer.target.type": "agent",
            }
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": agent_tool.name,
                "gen_ai.tool.type": "function",
                **transfer_attributes,
            }
            with _reference_tracer.start_as_current_span(
                f"execute_tool {agent_tool.name}", attributes=tool_span_attributes
            ) as tool_span:
                if tool_context.function_call_id:
                    tool_span.set_attribute("gen_ai.tool.call.id", tool_context.function_call_id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(args))
                sub_agent_span_attributes = {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.request.model": request_model,
                    "gen_ai.agent.name": specialist.name,
                }
                with _reference_tracer.start_as_current_span(
                    f"invoke_agent {specialist.name}", attributes=sub_agent_span_attributes
                ) as sub_agent_span:
                    result = await original_run_async(args=args, tool_context=tool_context)
                    sub_agent_span.set_attribute(
                        "gen_ai.output.messages",
                        json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": str(result)}]}]),
                    )
                tool_span.set_attribute("gen_ai.tool.call.result", str(result))
            return result

        root_agent = Agent(
            name="root_agent",
            description="Routes questions to specialist agents.",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="Delegate weather questions to the weather_specialist tool.",
            tools=[agent_tool],
        )
        session_service = InMemorySessionService()
        runner = Runner(agent=root_agent, app_name="delegation_app", session_service=session_service)

        async def _run():
            session = await session_service.create_session(app_name="delegation_app", user_id="test_user")
            agent_span_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.request.model": request_model,
                "gen_ai.agent.name": root_agent.name,
            }
            with _reference_tracer.start_as_current_span(
                "invoke_agent root_agent", attributes=agent_span_attributes
            ) as agent_span:
                agent_span.set_attribute("gen_ai.conversation.id", session.id)
                agent_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                last_text = ""
                async for event in runner.run_async(
                    user_id="test_user",
                    session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part(text=input_text)]),
                ):
                    if event.content and event.content.parts:
                        text = event.content.parts[0].text
                        if text:
                            last_text = text
                if last_text:
                    agent_span.set_attribute(
                        "gen_ai.output.messages",
                        json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": last_text}]}]),
                    )
                    print(f"    -> {last_text[:60]}")

        # `_patched_method` installs the caller-owned execute_tool run_async seam
        # and restores it in `finally`. The entry point stays runner.run_async.
        with _patched_method(agent_tool, "run_async", _traced_run_async):
            asyncio.run(_run())


def run_remote_a2a_agent_reference(topology_recorder):
    """Invoke a remote A2A agent from an ADK ``RemoteA2aAgent`` execution."""
    from a2a.helpers import get_message_text
    from google.adk.a2a import _compat as adk_a2a_compat
    from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    print("  [invoke_agent] RemoteA2aAgent -> A2A remote agent")

    with _run_a2a_server() as server_url, _suppress_adk_native_telemetry():
        remote_agent = RemoteA2aAgent(
            name="remote_weather_agent",
            agent_card=f"{server_url}{AGENT_CARD_WELL_KNOWN_PATH}",
        )
        session_service = InMemorySessionService()
        runner = Runner(agent=remote_agent, app_name="a2a_app", session_service=session_service)
        original_send_message = adk_a2a_compat.send_message

        async def _traced_send_message(client, *, request, request_metadata=None, context=None):
            agent_card = remote_agent._agent_card
            if agent_card is None:
                raise RuntimeError("RemoteA2aAgent did not resolve its Agent Card")
            target_url = urlparse(agent_card.supported_interfaces[0].url)
            client_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": agent_card.name,
                "gen_ai.provider.name": agent_card.provider.organization,
                "server.address": target_url.hostname or "localhost",
                "server.port": target_url.port or 443,
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_agent {agent_card.name}",
                kind=SpanKind.CLIENT,
                attributes=client_attributes,
            ) as client_span:
                if agent_card.description:
                    client_span.set_attribute("gen_ai.agent.description", agent_card.description)
                if request.context_id:
                    client_span.set_attribute("gen_ai.conversation.id", request.context_id)
                input_text = get_message_text(request, delimiter=" ")
                if input_text:
                    client_span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                    )
                async for response in original_send_message(
                    client,
                    request=request,
                    request_metadata=request_metadata,
                    context=context,
                ):
                    yield response

        async def _invoke():
            session = await session_service.create_session(app_name="a2a_app", user_id="test_user")
            input_text = "What's the weather in Seattle?"
            input_message = types.Content(role="user", parts=[types.Part(text=input_text)])
            parent_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": remote_agent.name,
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_agent {remote_agent.name}",
                kind=SpanKind.INTERNAL,
                attributes=parent_attributes,
            ) as parent_span:
                parent_span.set_attribute("gen_ai.conversation.id", session.id)
                parent_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                last_text = ""
                async for event in runner.run_async(
                    user_id="test_user",
                    session_id=session.id,
                    new_message=input_message,
                ):
                    if event.content and event.content.parts:
                        text = event.content.parts[0].text
                        if text:
                            last_text = text
                if last_text:
                    parent_span.set_attribute(
                        "gen_ai.output.messages",
                        json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": last_text}]}]),
                    )
                    print(f"    -> {last_text[:60]}")

        async def _run():
            try:
                await _invoke()
            finally:
                await remote_agent.cleanup()

        with _patched_method(adk_a2a_compat, "send_message", _traced_send_message):
            asyncio.run(_run())
        topology_recorder.assert_valid()


def main():
    print("=== Reference Implementation: Google ADK Reference Implementation ===")

    tp, lp, mp = setup_otel()

    span_counter = SpanCounter()
    tp.add_span_processor(span_counter)
    topology_recorder = A2ATopologyRecorder()
    tp.add_span_processor(topology_recorder)

    run_agent_reference()
    run_multi_agent_delegation_reference()
    run_remote_a2a_agent_reference(topology_recorder)
    run_memory_reference()

    print(f"\n  [diagnostic] Spans generated: {span_counter.count}")

    time.sleep(2)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
