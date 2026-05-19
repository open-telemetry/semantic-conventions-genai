"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling
against a mock OpenAI server, with manual OTel spans.
"""

import asyncio
import json
import os
import time

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
    asyncio.run(run_agent_with_handoff())

    flush_and_shutdown(tp, lp, mp)


async def run_agent_with_handoff():
    """Two-agent run that exercises the SDK's library-native Handoff path.

    A triage agent owns one Handoff to a billing specialist. The mock server
    prefers ``transfer_to_*`` tools when present, so the SDK's handoff
    machinery fires: it constructs a ``HandoffCallItem`` carrying the
    function tool call the model produced (``agents/items.py:266``) and a
    ``HandoffOutputItem`` carrying library-owned ``source_agent`` /
    ``target_agent`` references (``agents/items.py:276``). The SDK models
    handoff as a function tool call --- ``convert_handoff_tool`` at
    ``agents/models/chatcmpl_converter.py:864`` serializes each ``Handoff``
    as a ``ChatCompletionToolParam`` with ``"type": "function"``.

    To model the handoff in telemetry, this scenario emits:

    * one ``invoke_agent triage-agent`` span (the source agent),
    * one ``execute_tool transfer_to_billing_agent`` span as a child of the
      triage span, representing the handoff tool call,
    * one ``invoke_agent billing-agent`` span (the target agent).

    The ``execute_tool`` span carries both
    ``gen_ai.agent.handoff.source.name`` and
    ``gen_ai.agent.handoff.target.name``, sourced from
    ``HandoffOutputItem.source_agent.name`` and
    ``HandoffOutputItem.target_agent.name`` respectively. The source name
    is also derivable from the parent ``invoke_agent`` span's
    ``gen_ai.agent.name``, so emitting it explicitly is a convenience for
    queries that should not have to traverse parent-child links.

    ``RunHooks`` callbacks (``on_agent_start`` / ``on_agent_end`` /
    ``on_handoff`` from ``agents/lifecycle.py``) open and close each
    agent's ``invoke_agent`` span around its real execution. ``on_handoff``
    captures the parent-span context for the handoff event before closing
    the source agent's span; after ``Runner.run`` returns, the matching
    ``(HandoffCallItem, HandoffOutputItem)`` pair from ``result.new_items``
    is used to emit the ``execute_tool`` span with explicit timestamps and
    a parent context wrapping the source agent's ended span.
    """
    import openai
    from agents import Agent, Runner, handoff
    from agents.items import HandoffCallItem, HandoffOutputItem
    from agents.lifecycle import RunHooks
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from agents.tool import FunctionTool
    from opentelemetry.trace import NonRecordingSpan, set_span_in_context

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    request_model = "gpt-4o-mini"
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)
    host, port = mock_server_host_port(MOCK_BASE_URL)

    billing_agent = Agent(
        name="billing-agent",
        instructions="You are a billing specialist. Answer billing questions.",
        model=model,
    )
    triage_agent = Agent(
        name="triage-agent",
        instructions="You are a triage agent. Route billing questions to the billing specialist.",
        model=model,
        handoffs=[handoff(agent=billing_agent)],
    )
    input_text = "I have a question about my last invoice."

    print("  [agent_handoff] triage agent hands off to billing specialist (reference implementation)")

    # open_spans keeps active invoke_agent spans keyed by agent name so
    # on_agent_end (or on_handoff for the source agent that skips
    # on_agent_end) can close them. usage_totals accumulates per-agent
    # token counts across multiple LLM calls within the same agent turn
    # (matches the SDK's own context_wrapper.usage.add accumulation;
    # multi-turn agents would otherwise have only the last call's usage on
    # their span). finish_reasons_per_agent collects per-call finish
    # reasons derived from response.output[].type. handoff_events records
    # one entry per on_handoff firing, capturing the source span context
    # and the timestamp at the handoff boundary so the execute_tool span
    # can be emitted post-hoc with the correct parent and timing.
    open_spans: dict[str, object] = {}
    usage_totals: dict[str, dict[str, int]] = {}
    finish_reasons_per_agent: dict[str, list[str]] = {}
    handoff_events: list[dict] = []

    def _flush_per_agent_attrs(agent_name, agent_span):
        usage = usage_totals.pop(agent_name, None)
        if usage:
            if usage.get("input_tokens"):
                agent_span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
            if usage.get("output_tokens"):
                agent_span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
        finish_reasons = finish_reasons_per_agent.pop(agent_name, None)
        if finish_reasons:
            agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)

    class _SpanLifecycleHooks(RunHooks):
        async def on_agent_start(self_hooks, context, agent):
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
            # Use start_span (not start_as_current_span) because RunHooks
            # callbacks fire on different async tasks than the agent
            # execution they wrap; a context-manager-based span would try
            # to detach a Token created in a different Context. The span
            # still wraps the real agent execution lifetime: it opens here
            # at on_agent_start and closes at on_agent_end below.
            agent_span = _reference_tracer.start_span(f"invoke_agent {agent.name}", attributes=agent_span_attributes)
            open_spans[agent.name] = agent_span
            agent_span.set_attribute(
                "gen_ai.system_instructions",
                json.dumps([{"parts": [{"type": "text", "content": agent.instructions}]}]),
            )
            # Only the entry-point agent sees the user input directly; the
            # target of a handoff receives an SDK-rewritten transcript, not
            # the raw user text. Emit input.messages only on the triage
            # span, where it honestly reflects what the agent received.
            if agent.name == triage_agent.name:
                agent_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
            # Tool definitions: emit any function tools and any handoffs
            # the agent owns. Handoff is serialized as a ChatCompletionToolParam
            # by chatcmpl_converter.convert_handoff_tool, so from the
            # model's perspective it IS a tool. Handoff.tool_name,
            # tool_description, input_json_schema are library-owned
            # fields on agents/handoffs/__init__.py:Handoff.
            tool_defs = []
            for t in agent.tools:
                if isinstance(t, FunctionTool):
                    tool_defs.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.params_json_schema,
                            },
                        }
                    )
            for h in agent.handoffs:
                tool_defs.append(
                    {
                        "type": "function",
                        "function": {
                            "name": h.tool_name,
                            "description": h.tool_description,
                            "parameters": h.input_json_schema,
                        },
                    }
                )
            if tool_defs:
                agent_span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))

        async def on_agent_end(self_hooks, context, agent, output):
            agent_span = open_spans.pop(agent.name, None)
            if agent_span is None:
                return
            _flush_per_agent_attrs(agent.name, agent_span)
            if output is not None:
                agent_span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": str(output)}],
                            }
                        ]
                    ),
                )
            agent_span.end()

        async def on_llm_end(self_hooks, context, agent, response):
            # Library-owned response state: ModelResponse.usage carries
            # token counts (agents/items.py:651-666); response.output[].type
            # discriminates whether the model produced a final answer
            # ("message") or invoked a function/handoff ("function_call").
            # The latter maps to chat-completion finish_reason="tool_calls"
            # since the OpenAI Agents SDK serializes both function tools
            # and handoffs as ChatCompletionToolParam (see
            # chatcmpl_converter.convert_handoff_tool). We accumulate
            # tokens across multiple LLM calls per agent (mirrors the
            # SDK's own context_wrapper.usage.add accumulation at
            # run_loop.py:1628,1909) so multi-turn agents land their full
            # totals on their span at on_agent_end / on_handoff.
            if agent.name not in open_spans:
                return
            usage = getattr(response, "usage", None)
            if usage is not None:
                bucket = usage_totals.setdefault(agent.name, {"input_tokens": 0, "output_tokens": 0})
                input_tokens = getattr(usage, "input_tokens", None)
                output_tokens = getattr(usage, "output_tokens", None)
                if input_tokens is not None:
                    bucket["input_tokens"] += input_tokens
                if output_tokens is not None:
                    bucket["output_tokens"] += output_tokens
            output_items = getattr(response, "output", None) or []
            # Map response output to chat-completion finish_reason vocabulary.
            # Only emit when we have a clear library signal: function_call
            # items map to "tool_calls"; message items map to "stop". For
            # outputs containing only other item types (reasoning, MCP,
            # tool-search), omit rather than fabricate a finish state.
            item_types = {getattr(item, "type", None) for item in output_items}
            if "function_call" in item_types:
                finish_reasons_per_agent.setdefault(agent.name, []).append("tool_calls")
            elif "message" in item_types:
                finish_reasons_per_agent.setdefault(agent.name, []).append("stop")

        async def on_handoff(self_hooks, context, from_agent, to_agent):
            # The SDK only fires on_agent_end on the NextStepFinalOutput
            # path (turn_resolution.py:226 inside run_final_output_hooks);
            # the NextStepHandoff path at turn_resolution.py:513 skips it.
            # So for an agent that hands off, on_agent_end never fires.
            # Close the source agent's span here at the handoff boundary
            # so its duration honestly reflects the source agent's
            # execution time rather than the entire Runner.run lifetime.
            #
            # Before closing the source span, capture its SpanContext (the
            # immutable trace/span id pair) and a wall-clock timestamp so
            # the execute_tool span representing this handoff can be
            # emitted after Runner.run returns with the correct parent
            # span and accurate timing. Capturing here is necessary
            # because by the time we walk result.new_items at the end of
            # the run, both invoke_agent spans have ended; OpenTelemetry's
            # NonRecordingSpan + set_span_in_context lets a span be
            # attached to an already-closed parent via its SpanContext.
            from_span = open_spans.get(from_agent.name)
            captured_context = from_span.get_span_context() if from_span is not None else None
            handoff_events.append(
                {
                    "to_agent_name": to_agent.name,
                    "parent_span_context": captured_context,
                    "start_time_ns": time.time_ns(),
                }
            )
            from_span = open_spans.pop(from_agent.name, None)
            if from_span is not None:
                _flush_per_agent_attrs(from_agent.name, from_span)
                from_span.end()

    hooks = _SpanLifecycleHooks()
    result = await Runner.run(triage_agent, input_text, hooks=hooks)

    # Defensive: end any spans the SDK didn't close (shouldn't happen on
    # the happy path but keeps the trace coherent if Runner.run raises).
    while open_spans:
        _, agent_span = open_spans.popitem()
        agent_span.end()

    # Walk result.new_items for (HandoffCallItem, HandoffOutputItem) pairs.
    # Each HandoffCallItem.raw_item is the ResponseFunctionToolCall the
    # model produced -- carries call_id, name (transfer_to_<agent>), and
    # arguments. The HandoffOutputItem that follows carries the typed
    # source_agent / target_agent references the SDK assigned. Pairing is
    # positional: the SDK appends the call item at turn_resolution.py:1837
    # and the matching output item at turn_resolution.py:385 in lockstep.
    handoff_call_items = [item for item in result.new_items if isinstance(item, HandoffCallItem)]
    handoff_output_items = [item for item in result.new_items if isinstance(item, HandoffOutputItem)]
    if not handoff_output_items:
        # SDK behavior change, mock regression, or handoff not taken: fail
        # loudly rather than silently producing a misleading "direct only"
        # trace.
        raise AssertionError(
            "expected at least one HandoffOutputItem in result.new_items; "
            "scenario relies on the mock returning a transfer_to_* tool call"
        )

    # Pair each HandoffOutputItem with its originating HandoffCallItem by
    # call_id (HandoffOutputItem.raw_item is a tool-call-output keyed back
    # to the original ResponseFunctionToolCall.call_id; see
    # ItemHelpers.tool_call_output_item at
    # agents/run_internal/turn_resolution.py:387). Positional pairing
    # would mis-align in multi-handoffs-per-turn flows where the SDK
    # discards extra HandoffCallItems as ToolCallOutputItem
    # (turn_resolution.py:352-394), but only the first becomes a
    # HandoffOutputItem.
    call_items_by_id = {
        item.raw_item.call_id: item for item in handoff_call_items if getattr(item.raw_item, "call_id", None)
    }

    # Emit one execute_tool span per handoff event captured during the
    # run. Each execute_tool span is parented to the source agent's
    # invoke_agent span via the captured SpanContext, even though that
    # span has already ended. Per-handoff end_time captured inside the
    # loop so each span has its own honest end time (forward-compatible
    # with multi-handoff flows where spans should not all end at the
    # same instant).
    for idx, event in enumerate(handoff_events):
        if event["parent_span_context"] is None:
            # Reference demo: fail loudly rather than silently dropping
            # the execute_tool span. Production instrumentation would
            # likely fall back to the current OTel context, but in a
            # reference scenario a missing parent indicates a bug.
            raise AssertionError(
                f"on_handoff fired for {event['to_agent_name']} but the source agent's "
                "invoke_agent span was not open at that moment; cannot emit execute_tool span"
            )
        if idx >= len(handoff_output_items):
            raise AssertionError(
                f"more on_handoff events ({len(handoff_events)}) than HandoffOutputItems "
                f"({len(handoff_output_items)}); SDK state is inconsistent"
            )
        output_item = handoff_output_items[idx]
        output_call_id = (
            output_item.raw_item.get("call_id")
            if isinstance(output_item.raw_item, dict)
            else getattr(output_item.raw_item, "call_id", None)
        )
        call_item = call_items_by_id.get(output_call_id) if output_call_id else None
        if call_item is None:
            # Defensive: if we can't locate the originating call item by
            # call_id, fall back to positional pairing (matches single-
            # handoff-per-run flows which is what this scenario produces).
            if idx >= len(handoff_call_items):
                raise AssertionError(
                    f"no HandoffCallItem available for handoff event idx={idx} (call_id={output_call_id})"
                )
            call_item = handoff_call_items[idx]
        tool_call = call_item.raw_item
        parent_ctx = set_span_in_context(NonRecordingSpan(event["parent_span_context"]))
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_call.name,
        }
        tool_span = _reference_tracer.start_span(
            f"execute_tool {tool_call.name}",
            context=parent_ctx,
            start_time=event["start_time_ns"],
            attributes=tool_span_attributes,
        )
        # Library-owned values from the typed handoff items: call_id and
        # arguments come from the ResponseFunctionToolCall the model
        # produced; source.name / target.name come from the SDK-assigned
        # source_agent / target_agent references on HandoffOutputItem.
        if getattr(tool_call, "call_id", None):
            tool_span.set_attribute("gen_ai.tool.call.id", tool_call.call_id)
        if getattr(tool_call, "arguments", None) is not None:
            tool_span.set_attribute("gen_ai.tool.call.arguments", tool_call.arguments)
        tool_span.set_attribute("gen_ai.agent.handoff.source.name", output_item.source_agent.name)
        tool_span.set_attribute("gen_ai.agent.handoff.target.name", output_item.target_agent.name)
        tool_span.end(end_time=time.time_ns())

    target_name = handoff_output_items[0].target_agent.name
    print(f"    -> triage handed off to {target_name}, final output: {str(result.final_output)[:60]}")


if __name__ == "__main__":
    main()
