"""Reference implementation: external record join point instrumented over the OpenAI
Agents SDK guardrail runtime.

Exercises: invoke_agent around the SDK's own input guardrail evaluation, against a mock
chat completions server, with manual span instrumentation. The underlying OpenAI client
owns inference instrumentation.

The join point instrumented here is the SDK's own input guardrail evaluation
(InputGuardrail / Runner.run), a library-owned runtime object, not a hand-rolled gate. The
guardrail function below is a deterministic plain function (no extra LLM call) so both the
allow and block paths are reproducible against the mock server.
"""

import json
import os

from agents import Agent, GuardrailFunctionOutput, InputGuardrail, RunContextWrapper, Runner, function_tool
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tool import FunctionTool, ToolContext
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
REQUEST_MODEL = "gpt-4o-mini"
AGENT_NAME = "external_ref_agent"

_reference_tracer = reference_tracer()


def _blocked_topic_guardrail_function(
    ctx: RunContextWrapper[None], agent: Agent, input_text: str | list
) -> GuardrailFunctionOutput:
    """Deterministic input guardrail: trips on billing/refund requests, no LLM call."""
    text = input_text if isinstance(input_text, str) else json.dumps(input_text)
    tripwire_triggered = "refund" in text.lower()
    # The guardrail owns the out-of-band record and returns only its reference.
    record_ref = "01J9Z2K3M4N5P6Q7R8S9T0V1W3" if tripwire_triggered else "01J9Z2K3M4N5P6Q7R8S9T0V1W2"
    return GuardrailFunctionOutput(
        output_info={"checked_topic": "billing.refund", "record_ref": record_ref},
        tripwire_triggered=tripwire_triggered,
    )


# run_in_parallel=False makes this guardrail sequential: it runs and can raise
# InputGuardrailTripwireTriggered before the agent's first model turn starts, so a
# tripwire on the blocked run provably prevents any model call.
blocked_topic_guardrail = InputGuardrail(
    guardrail_function=_blocked_topic_guardrail_function,
    run_in_parallel=False,
)


def _input_messages(prompt: str) -> str:
    return json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt}]}])


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


async def run_allowed_reference(client) -> None:
    """Allowed run: guardrail does not trip, agent runs and calls a tool."""
    print("  [invoke_agent] allowed run with external reference")
    prompt = "Check the weather in Seattle."
    input_messages = _input_messages(prompt)

    request_model = REQUEST_MODEL
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)
    tools = [get_weather]
    agent = Agent(
        name=AGENT_NAME,
        instructions="You are a helpful assistant.",
        model=model,
        tools=tools,
        input_guardrails=[blocked_topic_guardrail],
    )

    agent_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent.name,
    }

    with _reference_tracer.start_as_current_span(
        f"invoke_agent {AGENT_NAME}",
        attributes=agent_attributes,
    ) as agent_span:
        agent_span.set_attribute("gen_ai.input.messages", input_messages)
        agent_span.set_attribute(
            "gen_ai.tool.definitions",
            json.dumps(
                [
                    {
                        "type": "function",
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.params_json_schema,
                    }
                    for t in tools
                    if isinstance(t, FunctionTool)
                ]
            ),
        )

        original_create = client.chat.completions.create
        captured_responses = []

        async def _capture_create(*args, **kwargs):
            response = await original_create(*args, **kwargs)
            captured_responses.append(response)
            return response

        client.chat.completions.create = _capture_create
        try:
            result = await Runner.run(agent, prompt)
        finally:
            client.chat.completions.create = original_create

        ref = result.input_guardrail_results[0].output.output_info["record_ref"]
        agent_span.set_attribute("gen_ai.external_ref", ref)
        usage = result.context_wrapper.usage
        if usage.total_tokens:
            agent_span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            agent_span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        finish_reasons = []
        if captured_responses:
            last_response = captured_responses[-1]
            finish_reasons = [
                choice.finish_reason
                for choice in getattr(last_response, "choices", []) or []
                if getattr(choice, "finish_reason", None)
            ]
            if finish_reasons:
                agent_span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        if result.final_output and finish_reasons:
            agent_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": str(result.final_output)}],
                            "finish_reason": finish_reasons[0],
                        }
                    ]
                ),
            )
        print(f"    -> allow: {str(result.final_output)[:60]}")


async def run_denied_reference(client) -> None:
    """Blocked run: guardrail trips, agent makes no model call."""
    print("  [invoke_agent] blocked run with external reference")
    prompt = "Refund the current invoice."
    input_messages = _input_messages(prompt)

    request_model = REQUEST_MODEL
    model = OpenAIChatCompletionsModel(model=request_model, openai_client=client)
    agent = Agent(
        name=AGENT_NAME,
        instructions="You are a helpful assistant.",
        model=model,
        input_guardrails=[blocked_topic_guardrail],
    )

    agent_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": agent.name,
    }

    with _reference_tracer.start_as_current_span(
        f"invoke_agent {AGENT_NAME}",
        attributes=agent_attributes,
    ) as agent_span:
        agent_span.set_attribute("gen_ai.input.messages", input_messages)
        try:
            await Runner.run(agent, prompt)
        except InputGuardrailTripwireTriggered as exc:
            ref = exc.guardrail_result.output.output_info["record_ref"]
            agent_span.set_attribute("gen_ai.external_ref", ref)
            # No model call happened (run_in_parallel=False on the guardrail stopped the
            # run before the first turn) and no execute_tool child span is emitted: the
            # run is terminal at the invoke_agent span itself.
            print("    -> block: refund request stopped before any model call")


def main() -> None:
    print("=== Reference Implementation: External Reference ===")

    tp, lp, mp = setup_otel()

    import asyncio

    import openai

    client = openai.AsyncOpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")

    async def _run_all():
        await run_allowed_reference(client)
        await run_denied_reference(client)

    asyncio.run(_run_all())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
