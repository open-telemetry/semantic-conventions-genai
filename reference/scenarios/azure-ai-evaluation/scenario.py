"""Reference implementation for Azure AI Evaluation."""

import inspect
import os

from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_evaluation():
    """Scenario: evaluation result event via Azure AI Evaluation."""
    from azure.ai.evaluation import OpenAIModelConfiguration, RelevanceEvaluator

    print("  [evaluate] Azure AI Evaluation relevance event")

    query = "What is the capital of France?"
    response = "Paris is the capital of France."
    model_config = OpenAIModelConfiguration(
        type="openai",
        api_key="mock-key",
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
    )
    evaluator = RelevanceEvaluator(model_config=model_config)
    evaluation_name = type(evaluator).__name__
    if evaluation_name.endswith("Evaluator"):
        evaluation_name = evaluation_name[: -len("Evaluator")]

    with _reference_tracer.start_as_current_span("reference.evaluation", kind=SpanKind.INTERNAL) as span:
        try:
            result = evaluator(query=query, response=response)
            score = float(result["relevance"])
            score_label = str(result["relevance_result"])
            attributes = {
                "gen_ai.evaluation.explanation": str(result["relevance_reason"]),
                "gen_ai.evaluation.name": evaluation_name,
                "gen_ai.evaluation.score.label": score_label,
                "gen_ai.evaluation.score.value": score,
                "gen_ai.evaluation.evaluator.id": f"azure-{evaluation_name.lower()}-{model_config.get('model', 'unknown')}",
            }

            is_llm_judge = hasattr(evaluator, "_model_config")
            attributes["gen_ai.evaluation.evaluator.type"] = "llm_judge" if is_llm_judge else "deterministic"

            sig = inspect.signature(evaluator.__call__)
            if "conversation" in sig.parameters or "messages" in sig.parameters:
                attributes["gen_ai.evaluation.scope"] = "full_run"
            else:
                attributes["gen_ai.evaluation.scope"] = "single_output"

            reference_event_logger("gen_ai.evaluation.reference").emit(
                event_name="gen_ai.evaluation.result",
                body="Evaluation result",
                attributes=attributes,
            )

            print(f"    -> score: {score}")
            print(f"    -> label: {score_label}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise


def main():
    print("=== Reference Implementation: Azure AI Evaluation Reference Implementation ===")

    tp, lp, mp = setup_otel()

    run_evaluation()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
