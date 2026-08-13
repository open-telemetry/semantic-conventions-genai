"""Reference implementation for DSPy.

Exercises: evaluation result events against a mock OpenAI server,
with manual OTel spans.
"""

import os

import dspy
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
MODEL_KEY = "openai/gpt-4o-mini"

_reference_tracer = reference_tracer()


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

    run_evaluation()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
