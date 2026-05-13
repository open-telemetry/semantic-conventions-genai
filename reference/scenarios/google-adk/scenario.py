"""Reference implementation for Google ADK."""

import asyncio
import contextlib
import json
import os
import time

from opentelemetry import trace as _trace
from opentelemetry.sdk.trace import SpanProcessor
from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()


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
def _suppress_adk_native_tracing():
    from google.adk import runners as adk_runners
    from google.adk.agents import base_agent as adk_base_agent
    from google.adk.flows.llm_flows import base_llm_flow as adk_base_llm_flow
    from google.adk.flows.llm_flows import functions as adk_functions
    from google.adk.telemetry import tracing as adk_tracing

    class _DisabledTracer:
        @contextlib.contextmanager
        def start_as_current_span(self, *_args, **_kwargs):
            yield _trace.NonRecordingSpan(_trace.INVALID_SPAN_CONTEXT)

    disabled_tracer = _DisabledTracer()
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
    host, port = mock_server_host_port(MOCK_BASE_URL)

    def get_weather(location: str, tool_context: ToolContext) -> str:
        """Get the current weather."""
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.type", "function")
            tool_span.set_attribute("gen_ai.tool.description", "Get the current weather.")
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

    with _suppress_adk_native_tracing():
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
                workflow_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                agent_span_attributes = {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.provider.name": "gcp.gemini",
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
                    agent_span.set_attribute("gen_ai.request.top_k", float(request_top_k))
                    agent_span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                    agent_span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                    agent_span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                    agent_span.set_attribute("gen_ai.conversation.id", session.id)
                    agent_span.set_attribute(
                        "gen_ai.system_instructions",
                        json.dumps([{"parts": [{"type": "text", "content": agent.instruction}]}]),
                    )
                    agent_span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                    )
                    agent_span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
                    span_attributes = {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.provider.name": "gcp.gemini",
                        "gen_ai.request.model": request_model,
                    }
                    if host:
                        span_attributes["server.address"] = host
                    if port is not None:
                        span_attributes["server.port"] = port
                    with _reference_tracer.start_as_current_span(
                        "chat gemini-2.0-flash", attributes=span_attributes
                    ) as span:
                        span.set_attribute("gen_ai.conversation.id", session.id)
                        span.set_attribute("gen_ai.request.choice.count", request_choice_count)
                        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
                        span.set_attribute("gen_ai.request.temperature", request_temperature)
                        span.set_attribute("gen_ai.request.top_p", request_top_p)
                        span.set_attribute("gen_ai.request.top_k", float(request_top_k))
                        span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                        span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                        span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                        span.set_attribute(
                            "gen_ai.system_instructions",
                            json.dumps([{"parts": [{"type": "text", "content": agent.instruction}]}]),
                        )
                        span.set_attribute(
                            "gen_ai.input.messages",
                            json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                        )
                        span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
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
                                span.set_attribute("gen_ai.usage.input_tokens", prompt_token_count)
                                agent_span.set_attribute("gen_ai.usage.input_tokens", prompt_token_count)
                            if candidate_token_count is not None:
                                span.set_attribute("gen_ai.usage.output_tokens", candidate_token_count)
                                agent_span.set_attribute("gen_ai.usage.output_tokens", candidate_token_count)
                        if finish_reason is not None:
                            span.set_attribute(
                                "gen_ai.response.finish_reasons",
                                [str(finish_reason).lower()],
                            )
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
                            span.set_attribute("gen_ai.output.messages", output_messages)
                            agent_span.set_attribute("gen_ai.output.messages", output_messages)
                            workflow_span.set_attribute("gen_ai.output.messages", output_messages)

        asyncio.run(_run())


def main():
    print("=== Reference Implementation: Google ADK Reference Implementation ===")

    tp, lp, mp = setup_otel()

    span_counter = SpanCounter()
    tp.add_span_processor(span_counter)

    run_agent_reference()

    print(f"\n  [diagnostic] Spans generated: {span_counter.count}")

    time.sleep(2)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
