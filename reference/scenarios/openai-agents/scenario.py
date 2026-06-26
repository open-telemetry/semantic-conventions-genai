"""Reference implementation for OpenAI Agents.

Exercises: agent run with tool calling
against a mock OpenAI server, with manual OTel spans.
"""

import asyncio
import copy
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
            "gen_ai.tool.name": "get_weather",
            "gen_ai.tool.type": "function",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.description", get_weather.description)
            if ctx.agent is not None and ctx.agent.name:
                tool_span.set_attribute("gen_ai.agent.name", ctx.agent.name)
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
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent.name,
    }
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

    Scenario shape and mock behavior
    --------------------------------
    A triage agent owns one Handoff to a billing specialist. The mock server
    prefers ``transfer_to_*`` tools when present, so the SDK's handoff
    machinery fires: it constructs a ``HandoffCallItem`` carrying the
    function tool call the model produced (``agents/items.py``) and a
    ``HandoffOutputItem`` carrying library-owned ``source_agent`` /
    ``target_agent`` references (``agents/run_internal/turn_resolution.py:385``).
    The SDK models handoff as a function tool call --- ``convert_handoff_tool``
    at ``agents/models/chatcmpl_converter.py:864`` serializes each ``Handoff``
    as a ``ChatCompletionToolParam`` with ``"type": "function"``.

    Telemetry shape
    ---------------
    The scenario emits three spans for one handoff:

    * one ``invoke_agent triage-agent`` span (the source agent),
    * one ``execute_tool transfer_to_billing_agent`` span as a child of the
      triage span, representing the handoff tool call,
    * one ``invoke_agent billing-agent`` span (the target agent).

    Instrumentation boundary
    ------------------------
    The ``execute_tool`` span wraps exactly the SDK's awaited handoff
    invocation at ``agents/run_internal/turn_resolution.py:369``
    (``await handoff.on_invoke_handoff(...)``). To install that span without
    forking the SDK, the scenario monkey-patches
    ``agents.run_internal.turn_resolution.execute_handoffs`` to a wrapper
    that swaps ``actual_handoff.handoff`` for a shallow copy with a wrapped
    ``on_invoke_handoff``. ``copy.copy`` is required (not
    ``dataclasses.replace``) so that ``Handoff._agent_ref`` (an
    ``init=False`` weakref set by the ``handoff()`` factory at
    ``agents/handoffs/__init__.py:334``) survives the replacement. The
    shared agent-owned ``Handoff`` object is never mutated;
    ``ToolRunHandoff`` is constructed fresh per turn at
    ``agents/run_internal/turn_resolution.py:1838``.

    The user-facing entry point remains ``Runner.run(triage_agent, ...)``.
    The patch is scenario-internal, applied before ``Runner.run`` and
    restored in a ``finally`` block.

    Value sources (all from typed SDK state at the call boundary)
    -------------------------------------------------------------
    * ``gen_ai.tool.name`` <- ``handoff_obj.tool_name`` (post-resolved per
      ``agents/handoffs/__init__.py:307``; honors ``tool_name_override``)
    * ``gen_ai.tool.call.id`` <- ``actual_handoff.tool_call.call_id``
    * ``gen_ai.tool.call.arguments`` <- ``actual_handoff.tool_call.arguments``
    * ``gen_ai.agent.handoff.source.name`` <- ``public_agent.name``
    * ``gen_ai.agent.handoff.target.name`` <- ``new_agent.name``
      (the return value of the wrapped ``on_invoke_handoff``)

    Regression assertions
    ---------------------
    After ``Runner.run`` returns successfully, the scenario asserts (a) at
    least one ``HandoffOutputItem`` appeared in ``result.new_items`` (mock-
    server regression guard) and (b) the count of emitted ``execute_tool``
    spans matches the ``HandoffOutputItem`` count (catches an SDK upgrade
    that would break the monkey-patch silently).

    ``RunHooks`` callbacks (``on_agent_start`` / ``on_agent_end`` /
    ``on_handoff`` from ``agents/lifecycle.py``) open and close each
    agent's ``invoke_agent`` span around its real execution. ``on_handoff``
    closes the source agent's ``invoke_agent`` span because the SDK skips
    ``on_agent_end`` on the ``NextStepHandoff`` path
    (``turn_resolution.py:513``).
    """
    import openai
    from agents import Agent, Runner, handoff
    from agents.items import HandoffOutputItem
    from agents.lifecycle import RunHooks
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from agents.run_internal import turn_resolution as _turn_resolution
    from agents.tool import FunctionTool
    from opentelemetry.trace import set_span_in_context

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
    # reasons derived from response.output[].type.
    open_spans: dict[str, object] = {}
    usage_totals: dict[str, dict[str, int]] = {}
    finish_reasons_per_agent: dict[str, list[str]] = {}

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
            usage = usage_totals.pop(agent.name, None)
            if usage:
                if usage.get("input_tokens"):
                    agent_span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
                if usage.get("output_tokens"):
                    agent_span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
            finish_reasons = finish_reasons_per_agent.pop(agent.name, None)
            if finish_reasons:
                agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
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
            from_span = open_spans.pop(from_agent.name, None)
            if from_span is None:
                return
            usage = usage_totals.pop(from_agent.name, None)
            if usage:
                if usage.get("input_tokens"):
                    from_span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
                if usage.get("output_tokens"):
                    from_span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
            finish_reasons = finish_reasons_per_agent.pop(from_agent.name, None)
            if finish_reasons:
                from_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
            from_span.end()

    hooks = _SpanLifecycleHooks()

    # Install execute_tool span emission around the SDK's awaited handoff
    # invocation at turn_resolution.py:369 (await handoff.on_invoke_handoff).
    # See the function docstring for the full rationale.
    _original_execute_handoffs = _turn_resolution.execute_handoffs
    _handoff_spans_emitted: list[None] = []

    async def _execute_handoffs_with_span(**kwargs):
        actual_handoff = kwargs["run_handoffs"][0]
        handoff_obj = actual_handoff.handoff
        tool_call = actual_handoff.tool_call
        public_agent = kwargs["public_agent"]
        source_span = open_spans.get(public_agent.name)
        if source_span is None:
            raise AssertionError(
                f"execute_handoffs fired for {public_agent.name} but its "
                "invoke_agent span is not open; cannot emit execute_tool span"
            )
        parent_ctx = set_span_in_context(source_span)
        original_on_invoke = handoff_obj.on_invoke_handoff

        async def _on_invoke_with_span(ctx, args):
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": handoff_obj.tool_name,
            }
            with _reference_tracer.start_as_current_span(
                f"execute_tool {handoff_obj.tool_name}",
                context=parent_ctx,
                attributes=tool_span_attributes,
            ) as tool_span:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_call.call_id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", tool_call.arguments)
                tool_span.set_attribute("gen_ai.agent.handoff.source.name", public_agent.name)
                new_agent = await original_on_invoke(ctx, args)
                tool_span.set_attribute("gen_ai.agent.handoff.target.name", new_agent.name)
                _handoff_spans_emitted.append(None)
                return new_agent

        # copy.copy preserves init=False fields (Handoff._agent_ref weakref
        # set by the handoff() factory at agents/handoffs/__init__.py:334).
        # dataclasses.replace would reset _agent_ref to None, breaking the
        # run-state snapshot/restore path that reads it at run_state.py:2606.
        # The shared agent-owned Handoff is never mutated; ToolRunHandoff is
        # per-turn (agents/run_internal/run_steps.py:60).
        wrapped = copy.copy(handoff_obj)
        wrapped.on_invoke_handoff = _on_invoke_with_span
        actual_handoff.handoff = wrapped
        return await _original_execute_handoffs(**kwargs)

    # The Runner.run call path re-reads `execute_handoffs` from this module
    # on each call: turn_resolution.execute_tools_and_side_effects captures
    # it locally at turn_resolution.py:573, and the post-interruption
    # resume path does the same at :782. Monkey-patching the module
    # attribute therefore takes effect on the next handoff.
    # agents/run_internal/run_loop.py:187-196 imports and re-exports
    # execute_handoffs at module import time but does not call it directly;
    # the call path always goes through execute_tools_and_side_effects.
    # Verified in openai-agents 0.4.x.
    _turn_resolution.execute_handoffs = _execute_handoffs_with_span
    try:
        result = await Runner.run(triage_agent, input_text, hooks=hooks)
    finally:
        _turn_resolution.execute_handoffs = _original_execute_handoffs
        # Defensive: end any spans the SDK didn't close (shouldn't happen
        # on the happy path but keeps the trace coherent if Runner.run
        # raised before our hooks closed everything).
        while open_spans:
            _, leftover_span = open_spans.popitem()
            leftover_span.end()

    handoff_output_items = [item for item in result.new_items if isinstance(item, HandoffOutputItem)]
    if not handoff_output_items:
        # SDK behavior change, mock regression, or handoff not taken: fail
        # loudly rather than silently producing a misleading "direct only"
        # trace.
        raise AssertionError(
            "expected at least one HandoffOutputItem in result.new_items; "
            "scenario relies on the mock returning a transfer_to_* tool call"
        )
    if len(_handoff_spans_emitted) != len(handoff_output_items):
        raise AssertionError(
            f"execute_tool span emission count ({len(_handoff_spans_emitted)}) "
            f"does not match HandoffOutputItem count ({len(handoff_output_items)}) "
            "on the fresh-Runner.run path used by this scenario; the "
            "execute_handoffs monkey-patch may not have been applied -- verify "
            "openai-agents SDK compatibility with execute_tools_and_side_effects "
            "re-reading execute_handoffs per call (turn_resolution.py:573, also "
            ":782 for the post-interruption resume path). Note: this 1:1 "
            "invariant holds only for fresh Runner.run; run-state restore can "
            "reconstruct HandoffOutputItem without invoking on_invoke_handoff "
            "(run_state.py:3248-3255)."
        )

    target_name = handoff_output_items[0].target_agent.name
    print(f"    -> triage handed off to {target_name}, final output: {str(result.final_output)[:60]}")


if __name__ == "__main__":
    main()
