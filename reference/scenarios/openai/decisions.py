"""Decision inference through the real SDK and a documented-shape HTTP mock.

API contract: https://developers.openai.com/api/reference/resources/decisions/methods/create
The fixture predictions are synthetic. They exercise SDK parsing, not model quality.
"""

import json
from time import time_ns

import httpx2
from openai import BadRequestError, OpenAI
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, reference_event_logger, reference_meter, reference_tracer, setup_otel


def decision_request(client, *, model, input, questions, capture_results=False, results_on_event=False):
    """Instrument one Decisions SDK call, including all its returned answers."""
    attributes = {
        "gen_ai.operation.name": "decision",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": model,
        "server.address": client.base_url.host,
        "server.port": client.base_url.port or (443 if client.base_url.scheme == "https" else 80),
    }
    meter = reference_meter()
    duration = meter.create_histogram("gen_ai.client.inference.duration", unit="s")
    started = time_ns()
    with reference_tracer().start_as_current_span(
        f"decision {model}",
        kind=SpanKind.CLIENT,
        attributes=attributes,
        start_time=started,
        end_on_exit=False,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            response = client.decisions.create(model=model, input=input, questions=questions)
            span.set_attribute("gen_ai.response.model", response.model)
            attributes["gen_ai.response.model"] = response.model
            if capture_results:
                results = []
                # OpenAI guarantees answer order matches request question order.
                for index, answer in enumerate(response.answers):
                    result = {"question_index": index, "type": answer.type}
                    if answer.name is not None:
                        result["question_name"] = answer.name
                    if answer.type == "predicate":
                        result["probability"] = answer.probability
                    elif answer.type == "choice":
                        result["value"] = answer.choice
                        for option in answer.probabilities:
                            if type(option.value) is type(answer.choice) and option.value == answer.choice:
                                result["probability"] = option.probability
                                break
                    elif answer.type == "score":
                        # The API's score is an expected index into these request levels.
                        levels = questions[index].get("levels", [])
                        if len(levels) < 2 or any(not isinstance(level.get("label"), str) for level in levels):
                            continue
                        result["value"] = answer.score
                        result["levels"] = [level["label"] for level in levels]
                    elif answer.type != "refusal":
                        # Unknown future answers are not abstentions or refusals.
                        continue
                    results.append(result)
                if results:
                    if results_on_event:
                        reference_event_logger().emit(
                            event_name="gen_ai.client.inference.operation.details",
                            severity_number=SeverityNumber.DEBUG,
                            attributes={**attributes, "gen_ai.decision.results": results},
                        )
                    else:
                        span.set_attribute("gen_ai.decision.results", json.dumps(results))
            # Usage belongs to the request, including when some questions are refused.
            for direction, tokens in (
                ("input", response.usage.input_tokens),
                ("output", response.usage.output_tokens),
            ):
                if tokens is not None:
                    span.set_attribute(f"gen_ai.usage.{direction}_tokens", tokens)
                    meter.create_histogram(
                        f"gen_ai.client.inference.operation.{direction}_tokens", unit="{token}"
                    ).record(tokens, attributes)
                    meter.create_counter(f"gen_ai.client.inference.usage.{direction}_tokens", unit="{token}").add(
                        tokens, {**attributes, "gen_ai.token.modality": "unknown"}
                    )
            return response
        except Exception as error:
            error_type = type(error).__qualname__
            span.set_attribute("error.type", error_type)
            span.set_status(StatusCode.ERROR)
            attributes["error.type"] = error_type
            raise
        finally:
            finished = time_ns()
            span.end(end_time=finished)
            duration.record((finished - started) / 1_000_000_000, attributes)


def cases():
    """SDK request arguments paired with mock responses from the documented schema."""
    routing_question = {
        "type": "choice",
        "name": "department",
        "instructions": "Which team should handle this request?",
        "choices": [{"value": "billing"}, {"value": "technical"}, {"value": "sales"}],
    }
    routing_answer = {
        "type": "choice",
        "name": "department",
        "choice": "technical",
        "probabilities": [
            {"value": "billing", "probability": 0.2},
            {"value": "technical", "probability": 0.72},
            {"value": "sales", "probability": 0.08},
        ],
        "confidence": 0.55,
    }
    yield (
        "Checkout returns an error when I submit an order.",
        [routing_question],
        [routing_answer],
    )
    yield (
        "Query: reset a password. Passage: choose Forgot password to reset it.",
        [
            {
                "type": "score",
                "name": "relevance",
                "instructions": "How useful is the passage for answering the query?",
                "levels": [{"label": "irrelevant"}, {"label": "relevant"}],
            }
        ],
        [
            {
                "type": "score",
                "name": "relevance",
                "score": 0.84,
                "confidence": 0.6,
                "probabilities": [
                    {"value": 0, "label": "irrelevant", "probability": 0.16},
                    {"value": 1, "label": "relevant", "probability": 0.84},
                ],
            }
        ],
    )
    yield (
        "Please escalate this request.",
        [
            {"type": "predicate", "instructions": "Does the user request escalation?"},
            {
                "type": "choice",
                "name": "escalate",
                "instructions": "Should the request be escalated?",
                "choices": [{"value": True}, {"value": "true"}],
            },
        ],
        [
            {"type": "predicate", "probability": 0.87},
            {
                "type": "choice",
                "name": "escalate",
                "choice": True,
                "probabilities": [
                    {"value": "true", "probability": 0.13},
                    {"value": True, "probability": 0.87},
                ],
                "confidence": 0.74,
            },
        ],
    )
    yield (
        "Synthetic input exercising partial refusal, without inferring its cause.",
        [
            routing_question,
            {"type": "predicate", "name": "urgent", "instructions": "Is the request urgent?"},
        ],
        [routing_answer, {"type": "refusal", "name": "urgent"}],
    )


def mock_client(expected_input, expected_questions, answers, *, status_code=200):
    """Intercept HTTP after real SDK serialization; parse responses through the SDK."""

    def handle(request):
        assert request.method == "POST"
        assert request.url.path == "/v1/decisions"
        body = json.loads(request.content)
        assert body["input"] == expected_input
        assert body["questions"] == expected_questions
        assert body["model"] == "gpt-6-luna"
        if status_code != 200:
            return httpx2.Response(
                status_code,
                json={"error": {"message": "Invalid request", "type": "invalid_request_error", "code": None}},
            )
        return httpx2.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "answers": answers,
                "usage": {
                    "input_tokens": 42,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens": 0,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 42,
                },
            },
        )

    return OpenAI(
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def main():
    providers = setup_otel()
    try:
        for input_text, questions, answers in cases():
            with mock_client(input_text, questions, answers) as client:
                response = decision_request(
                    client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
                )
                assert len(response.answers) == len(questions)
                for actual, expected in zip(response.answers, answers, strict=True):
                    assert actual.type == expected["type"]
                    if actual.type == "choice":
                        assert actual.choice == expected["choice"]
                    elif actual.type == "score":
                        assert actual.score == expected["score"]
        input_text, questions, answers = list(cases())[-1]
        with mock_client(input_text, questions, answers) as client:
            decision_request(
                client,
                model="gpt-6-luna",
                input=input_text,
                questions=questions,
                capture_results=True,
                results_on_event=True,
            )
        input_text, questions, answers = next(cases())
        with mock_client(input_text, questions, answers, status_code=400) as client:
            try:
                decision_request(
                    client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
                )
            except BadRequestError:
                print("Expected SDK request error recorded.")
            else:
                raise AssertionError("The error scenario unexpectedly succeeded")
    finally:
        flush_and_shutdown(*providers)


if __name__ == "__main__":
    main()
