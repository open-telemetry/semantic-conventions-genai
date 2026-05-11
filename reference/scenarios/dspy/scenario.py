"""Reference implementation for DSPy.

Exercises: chat via DSPy LM and evaluation result events
against a mock OpenAI server, with manual OTel spans.
"""

import json
import os

import dspy
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
MODEL_KEY = "openai/gpt-4o-mini"

_reference_tracer = reference_tracer()


def run_chat():
    """Scenario: basic chat via DSPy LM with reference implementation."""
    print("  [chat] basic chat via DSPy LM (reference implementation)")

    request_model = "gpt-4o-mini"
    lm_model = f"openai/{request_model}"
    prompt_text = "Say hello."
    lm = dspy.LM(
        model=lm_model,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        cache=False,
    )
    dspy.configure(lm=lm)

    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        result = lm(prompt_text)
        history_entry = lm.history[-1] if lm.history else None
        if history_entry is not None:
            request_messages = history_entry.get("messages") or []
            span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {
                            "role": message["role"],
                            "parts": [{"type": "text", "content": message["content"]}],
                        }
                        for message in request_messages
                        if isinstance(message.get("content"), str)
                    ]
                ),
            )
            response = history_entry.get("response")
            if response is not None:
                if getattr(response, "model", None):
                    span.set_attribute("gen_ai.response.model", response.model)
                if getattr(response, "id", None):
                    span.set_attribute("gen_ai.response.id", response.id)
                finish_reasons = [
                    str(choice.finish_reason).lower()
                    for choice in response.choices
                    if getattr(choice, "finish_reason", None)
                ]
                if finish_reasons:
                    span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
                span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": choice.message.content}],
                                "finish_reason": choice.finish_reason,
                            }
                            for choice in response.choices
                            if getattr(choice.message, "content", None)
                        ]
                    ),
                )
        usage = lm.history[-1].get("usage", {}) if lm.history else {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
        if completion_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
        }
        if history_entry is not None:
            if request_messages:
                event_attrs["gen_ai.input.messages"] = json.dumps(
                    [
                        {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]}
                        for m in request_messages
                        if isinstance(m.get("content"), str)
                    ]
                )
            response = history_entry.get("response")
            if response is not None:
                if getattr(response, "model", None):
                    event_attrs["gen_ai.response.model"] = response.model
                if getattr(response, "id", None):
                    event_attrs["gen_ai.response.id"] = response.id
                finish_reasons = [
                    str(choice.finish_reason).lower()
                    for choice in response.choices
                    if getattr(choice, "finish_reason", None)
                ]
                if finish_reasons:
                    event_attrs["gen_ai.response.finish_reasons"] = finish_reasons
                event_attrs["gen_ai.output.messages"] = json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": choice.message.content}],
                            "finish_reason": choice.finish_reason,
                        }
                        for choice in response.choices
                        if getattr(choice.message, "content", None)
                    ]
                )
        if prompt_tokens is not None:
            event_attrs["gen_ai.usage.input_tokens"] = prompt_tokens
        if completion_tokens is not None:
            event_attrs["gen_ai.usage.output_tokens"] = completion_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {str(result)[:60]}")


def run_tool_call():
    """Scenario: tool calling via DSPy ReAct with reference implementation."""
    print("  [chat_tool_call] tool calling via DSPy ReAct (reference implementation)")

    request_model = "gpt-4o-mini"
    lm_model = f"openai/{request_model}"
    prompt_text = "What's the weather in Seattle?"
    lm = dspy.LM(
        model=lm_model,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        cache=False,
    )
    dspy.configure(lm=lm)
    messages = [{"role": "user", "content": prompt_text}]
    tool_definition = {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "parameters": {
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
            "type": "object",
        },
    }
    request_tool = {
        "type": "function",
        "function": tool_definition,
    }

    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps([request_tool]))
        result = lm(
            messages=messages,
            tools=[request_tool],
        )
        history_entry = lm.history[-1] if lm.history else None
        if history_entry is not None:
            request_messages = history_entry.get("messages") or []
            span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {
                            "role": message["role"],
                            "parts": [{"type": "text", "content": message["content"]}],
                        }
                        for message in request_messages
                        if isinstance(message.get("content"), str)
                    ]
                ),
            )
            response = history_entry.get("response")
            if response is not None:
                if getattr(response, "id", None):
                    span.set_attribute("gen_ai.response.id", response.id)
                finish_reasons = [
                    str(choice.finish_reason).lower()
                    for choice in response.choices
                    if getattr(choice, "finish_reason", None)
                ]
                if finish_reasons:
                    span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
                span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": choice.message.content}],
                                "finish_reason": choice.finish_reason,
                            }
                            for choice in response.choices
                            if getattr(choice.message, "content", None)
                        ]
                    ),
                )
        usage = lm.history[-1].get("usage", {}) if lm.history else {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
        if completion_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
        print(f"    -> {str(result)[:60]}")


class EchoProgram(dspy.Module):
    def forward(self, question):
        result = dspy.settings.lm(question)
        text = result[0] if isinstance(result, list) else str(result)
        return dspy.Prediction(answer=text)


def contains_mock_response(_example, prediction, trace=None):
    del trace
    return float("mock response" in getattr(prediction, "answer", "").lower())


def run_evaluation():
    """Scenario: evaluation result event with reference implementation."""
    print("  [evaluate] DSPy evaluation result event")

    lm = dspy.LM(
        model=MODEL_KEY,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        cache=False,
    )
    dspy.configure(lm=lm, track_usage=True)

    devset = [
        dspy.Example(
            question="Say hello.",
            answer="This is a mock response from the mock server.",
        ).with_inputs("question"),
    ]

    evaluate = dspy.Evaluate(
        devset=devset,
        metric=contains_mock_response,
        display_progress=False,
        display_table=False,
    )

    with _reference_tracer.start_as_current_span("reference.evaluation", kind=SpanKind.INTERNAL) as span:
        try:
            result = evaluate(EchoProgram())
            score = float(result.score)
            score_label = "pass" if score > 0 else "fail"

            attributes = {
                "gen_ai.evaluation.name": contains_mock_response.__name__,
                "gen_ai.evaluation.score.label": score_label,
                "gen_ai.evaluation.score.value": score,
            }
            reference_event_logger("gen_ai.evaluation.reference").emit(
                event_name="gen_ai.evaluation.result",
                body="Evaluation result",
                attributes=attributes,
            )

            print(f"    -> score: {result.score}")
            print(f"    -> results: {len(result.results)}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            raise


def main():
    print("=== Reference Implementation: DSPy ===")

    tp, lp, mp = setup_otel()

    run_chat()
    run_tool_call()
    run_evaluation()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
