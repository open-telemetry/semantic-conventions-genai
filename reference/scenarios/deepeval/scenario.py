"""Reference implementation for DeepEval.

Changes vs upstream:
- Added gen_ai.response.id to the evaluation result event.
  This field correlates the evaluation back to the specific LLM completion
  being evaluated, as required by the gen_ai.evaluation.result event spec.
  In a real pipeline the response_id comes from the LLM call that produced
  the output being evaluated; here we use a deterministic mock value so the
  reference scenario stays self-contained and reproducible.
"""

import os

from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()

# Simulates the response id from the upstream LLM call whose output is
# being evaluated.  In production this would be captured from the inference
# span (gen_ai.response.id) and passed into the evaluation step.
_MOCK_RESPONSE_ID = "chatcmpl-mockEvalRef0001"


def run_evaluation():
    """Scenario: evaluation result event via DeepEval GEval."""
    from deepeval.metrics import GEval
    from deepeval.models import GPTModel
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    print("  [evaluate] DeepEval relevance evaluation event")

    metric = GEval(
        name="relevance",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        evaluation_steps=[
            "Check whether the actual output correctly answers the user input.",
        ],
        model=GPTModel(
            model="o1-mini",
            _openai_api_key="mock-key",
            base_url=MOCK_BASE_URL,
        ),
        async_mode=False,
    )
    test_case = LLMTestCase(
        input="What is the capital of France?",
        actual_output="Paris is the capital of France.",
        expected_output="Paris is the capital of France.",
    )

    def _stub_generate(_prompt, schema=None):
        del schema
        return (
            '{"score": 9, "reason": "The output correctly identifies Paris as the capital of France."}',
            0.0,
        )

    metric.model.generate = _stub_generate

    with _reference_tracer.start_as_current_span("reference.evaluation", kind=SpanKind.INTERNAL) as span:
        try:
            score = float(metric.measure(test_case))
            attributes = {
                "gen_ai.evaluation.name": metric.name,
                "gen_ai.evaluation.score.value": score,
                # Correlates this evaluation back to the LLM completion being
                # evaluated.  Populated when the response id is available from
                # the upstream inference call.
                "gen_ai.response.id": _MOCK_RESPONSE_ID,
            }
            if getattr(metric, "reason", None):
                attributes["gen_ai.evaluation.explanation"] = metric.reason
            reference_event_logger("gen_ai.evaluation.reference").emit(
                event_name="gen_ai.evaluation.result",
                body="Evaluation result",
                attributes=attributes,
            )

            print(f"    -> score: {score}")
            if getattr(metric, "reason", None):
                print(f"    -> explanation: {metric.reason}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def main():
    print("=== Reference Implementation: DeepEval Reference Implementation ===")

    # DeepEval uses litellm which respects OPENAI_API_BASE.
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    os.environ["OPENAI_API_KEY"] = "mock-key"
    os.environ["OPENAI_API_BASE"] = MOCK_BASE_URL

    tp, lp, mp = setup_otel()

    run_evaluation()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
