"""Reference implementation for Google ADK."""

import asyncio
import contextlib
import json
import os
import time

from opentelemetry import trace as _trace
from opentelemetry.sdk.trace import SpanProcessor
from reference_shared import (
    flush_and_shutdown,
    reference_event_logger,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

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


def run_resumable_execution_reference():
    """Scenario: ADK confirmation pause and resumable execution."""
    from google.adk.agents import Agent
    from google.adk.apps import App, ResumabilityConfig
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import FunctionTool
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types

    print("  [resumable_execution] ADK confirmation pause and resume")

    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")
    tool_execution_count = 0

    def record_agent_response_attributes(span, event) -> None:
        usage_metadata = getattr(event, "usage_metadata", None)
        if usage_metadata is not None:
            input_tokens = getattr(usage_metadata, "prompt_token_count", None)
            output_tokens = getattr(usage_metadata, "candidates_token_count", None)
            if input_tokens is not None:
                span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            if output_tokens is not None:
                span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        finish_reason = getattr(event, "finish_reason", None)
        if finish_reason is not None:
            span.set_attribute(
                "gen_ai.response.finish_reasons",
                [str(getattr(finish_reason, "value", finish_reason)).lower()],
            )

    def submit_change(tool_context: ToolContext) -> dict[str, str]:
        """Submit the pending change after the caller confirms it."""
        nonlocal tool_execution_count
        tool_execution_count += 1
        tool_context.state["approval_status"] = "accepted"
        with _reference_tracer.start_as_current_span(
            "execute_tool submit_change",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": "submit_change",
                "gen_ai.tool.type": "function",
            },
        ) as tool_span:
            if not tool_context.invocation_id:
                raise RuntimeError("ADK did not expose an invocation ID to the tool.")
            if tool_context.function_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_context.function_call_id)
        # This return value is consumed by ADK, but is intentionally not recorded
        # in telemetry.
        return {"status": "accepted"}

    with _suppress_adk_native_telemetry():
        agent = Agent(
            name="resumable_confirmation_agent",
            model=Gemini(model="gemini-2.0-flash", base_url=MOCK_BASE_URL),
            tools=[FunctionTool(submit_change, require_confirmation=True)],
        )
        app = App(
            name="resumable_confirmation_app",
            root_agent=agent,
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        session_service = InMemorySessionService()
        runner = Runner(app=app, session_service=session_service)

        async def _run():
            session = await session_service.create_session(
                app_name=app.name,
                user_id="test_user",
            )
            execution_id = None
            original_tool_call_id = None
            confirmation_call_id = None
            confirmation_response_name = None
            confirmation_calls = []

            with _reference_tracer.start_as_current_span(
                "invoke_workflow resumable_confirmation_app",
                attributes={
                    "gen_ai.operation.name": "invoke_workflow",
                    "gen_ai.workflow.name": app.name,
                },
            ):
                with _reference_tracer.start_as_current_span(
                    "invoke_agent resumable_confirmation_agent",
                    attributes={
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.agent.name": agent.name,
                        "gen_ai.request.model": agent.model.model,
                    },
                ) as suspended_agent_span:
                    async for event in runner.run_async(
                        user_id="test_user",
                        session_id=session.id,
                        new_message=types.Content(
                            role="user",
                            parts=[types.Part(text="Submit the pending change.")],
                        ),
                    ):
                        record_agent_response_attributes(suspended_agent_span, event)
                        if not event.invocation_id:
                            raise RuntimeError("ADK emitted an event without an invocation ID.")
                        if execution_id is None:
                            execution_id = event.invocation_id
                        elif event.invocation_id != execution_id:
                            raise RuntimeError("ADK changed the invocation ID before suspension.")

                        if event.actions.requested_tool_confirmations:
                            if len(event.actions.requested_tool_confirmations) != 1:
                                raise RuntimeError("Expected one ADK tool confirmation request.")
                            original_tool_call_id = next(iter(event.actions.requested_tool_confirmations))

                        for function_call in event.get_function_calls():
                            original_call = (function_call.args or {}).get("originalFunctionCall")
                            if isinstance(original_call, dict):
                                confirmation_calls.append(function_call)

                matching_confirmation_calls = [
                    call
                    for call in confirmation_calls
                    if (call.args or {}).get("originalFunctionCall", {}).get("id") == original_tool_call_id
                ]
                if len(matching_confirmation_calls) == 1:
                    confirmation_call_id = matching_confirmation_calls[0].id
                    confirmation_response_name = matching_confirmation_calls[0].name

                if (
                    execution_id is None
                    or original_tool_call_id is None
                    or confirmation_call_id is None
                    or confirmation_response_name is None
                ):
                    raise RuntimeError("ADK did not emit a resumable confirmation event.")
            confirmation_response = types.Part.from_function_response(
                name=confirmation_response_name,
                response={"confirmed": True},
            )
            confirmation_response.function_response.id = confirmation_call_id
            resumed_final_response = False
            resumed_event_seen = False
            state_delta_seen = False

            with _reference_tracer.start_as_current_span(
                "invoke_workflow resumable_confirmation_app",
                attributes={
                    "gen_ai.operation.name": "invoke_workflow",
                    "gen_ai.workflow.name": app.name,
                },
            ):
                with _reference_tracer.start_as_current_span(
                    "invoke_agent resumable_confirmation_agent",
                    attributes={
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.agent.name": agent.name,
                        "gen_ai.request.model": agent.model.model,
                    },
                ) as resumed_agent_span:
                    async for event in runner.run_async(
                        user_id="test_user",
                        session_id=session.id,
                        invocation_id=execution_id,
                        new_message=types.Content(
                            role="user",
                            parts=[confirmation_response],
                        ),
                    ):
                        record_agent_response_attributes(resumed_agent_span, event)
                        if event.invocation_id != execution_id:
                            raise RuntimeError("ADK resumed a different invocation.")
                        if not resumed_event_seen:
                            resumed_event_seen = True
                        state_delta = event.actions.state_delta
                        if state_delta:
                            if state_delta_seen:
                                raise RuntimeError("Expected one ADK state delta for the tool execution.")
                            state_delta_seen = True
                            reference_event_logger().emit(
                                event_name="gen_ai.execution.state.changed",
                                body="Execution state changed",
                                attributes={
                                    "gen_ai.execution.state.changed_key.count": len(state_delta),
                                },
                            )
                        resumed_final_response = resumed_final_response or event.is_final_response()

                if not resumed_event_seen or not resumed_final_response or not state_delta_seen:
                    raise RuntimeError("ADK did not prove completion in the resumed event stream.")

            if tool_execution_count != 1:
                raise RuntimeError("Expected the confirmation-gated tool to execute once.")

        asyncio.run(_run())


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


def main():
    print("=== Reference Implementation: Google ADK Reference Implementation ===")

    tp, lp, mp = setup_otel()

    span_counter = SpanCounter()
    tp.add_span_processor(span_counter)

    run_agent_reference()
    run_resumable_execution_reference()
    run_memory_reference()

    print(f"\n  [diagnostic] Spans generated: {span_counter.count}")

    time.sleep(2)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
