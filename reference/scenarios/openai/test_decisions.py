"""Check request-scoped telemetry using real SDK calls and in-memory exporters."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scenario as decisions
from jsonschema import Draft202012Validator, ValidationError
from openai import BadRequestError
from openai.types.decision import (
    AnswerAnswerResourceChoice,
    AnswerAnswerResourcePredicate,
    AnswerAnswerResourceRefusal,
    AnswerAnswerResourceScore,
)
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

spec = importlib.util.spec_from_file_location(
    "content_models", Path(__file__).resolve().parents[3] / "docs/gen-ai/non-normative/models.py"
)
content_models = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = content_models
spec.loader.exec_module(content_models)
RESULT_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "model/gen-ai/gen-ai-decision-results.json").read_text(encoding="utf-8")
)
RESULT_VALIDATOR = Draft202012Validator(RESULT_SCHEMA)


# Published OpenAI answer excerpts and the request context needed to interpret
# them. These are parsed as SDK answer types; no synthetic response envelope is
# added around the excerpts.
# https://developers.openai.com/api/docs/guides/decisions
OPENAI_CHOICE_QUESTION = {
    "type": "choice",
    "name": "department",
    "instructions": "Which department should handle this complaint?",
    "choices": [
        {"value": "billing", "description": "Payments, invoices, and refunds."},
        {"value": "technical", "description": "Problems using the product."},
        {"value": "shipping", "description": "Delivery and tracking."},
        {"value": "other", "description": "Requests outside these categories."},
    ],
}
OPENAI_CHOICE_ANSWER = {
    "type": "choice",
    "name": "department",
    "choice": "billing",
    "probabilities": [
        {"value": "billing", "probability": 0.95},
        {"value": "technical", "probability": 0.02},
        {"value": "shipping", "probability": 0.01},
        {"value": "other", "probability": 0.02},
    ],
    "confidence": 0.93,
}

# The complete request levels and response excerpt are from the same guide.
OPENAI_SCORE_QUESTION = {
    "type": "score",
    "name": "severity",
    "instructions": "How severe is this issue?",
    "levels": [
        {"label": "Cosmetic", "description": "Appearance only; no lost functionality."},
        {"label": "Workaround available", "description": "A task fails, but another way works."},
        {"label": "Fully blocked", "description": "A task fails with no workaround."},
    ],
}
OPENAI_SCORE_ANSWER = {
    "type": "score",
    "name": "severity",
    "score": 1.1,
    "probabilities": [
        {"value": 0, "label": "Cosmetic", "probability": 0.1},
        {"value": 1, "label": "Workaround available", "probability": 0.7},
        {"value": 2, "label": "Fully blocked", "probability": 0.2},
    ],
    "confidence": 0.55,
}

# OpenAI documents the refusal response type and fields, but not a literal
# refusal payload. This shape fixture uses the documented question name.
OPENAI_REFUSAL_ANSWER = {"type": "refusal", "name": "department"}


# These raw JSON response fixtures are copied from TypeSafe's published
# System One and primitive examples. They exercise the HTTP contract only; no
# TypeSafe SDK or live service is involved.
# Noul request/response: https://docs.typesafe.ai/primitives/noul
JEV_NOUL_QUESTIONS = {
    "is_human_escalation": {"type": "noul"},
    "is_repeat_contact": {"type": "noul"},
}
JEV_NOUL_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "is_human_escalation": {"type": "noul", "noul": 0.99},
        "is_repeat_contact": {"type": "noul", "noul": 0.93},
    },
    "usage": {"input_tokens": 360, "output_tokens": 39},
}

# Choice request order and response: https://docs.typesafe.ai/primitives/choice
JEV_CHOICE_QUESTIONS = {
    "department": {"type": "choice"},
    "return_reason": {"type": "choice"},
    "shipping_issue": {"type": "choice"},
    "requested_resolution": {"type": "choice"},
    "tone": {"type": "choice"},
}
JEV_CHOICE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "department": {
            "type": "choice",
            "choice": "returns",
            "confidence": 0.42,
            "probabilities": {"shipping": 0.04, "billing": 0.35, "returns": 0.61},
        },
        "return_reason": {
            "type": "choice",
            "choice": "wrong_size",
            "confidence": 1.0,
            "probabilities": {"other": 0.0, "wrong_size": 1.0, "changed_mind": 0.0, "damaged": 0.0, "wrong_item": 0.0},
        },
        "shipping_issue": {
            "type": "choice",
            "choice": "delayed",
            "confidence": 0.67,
            "probabilities": {
                "wrong_address": 0.0,
                "other": 0.26,
                "not_delivered": 0.0,
                "damaged_in_transit": 0.0,
                "delayed": 0.74,
            },
        },
        "requested_resolution": {
            "type": "choice",
            "choice": "refund",
            "confidence": 0.2,
            "probabilities": {"replacement": 0.34, "refund": 0.4, "information": 0.02, "exchange": 0.24},
        },
        "tone": {
            "type": "choice",
            "choice": "frustrated",
            "confidence": 0.76,
            "probabilities": {"frustrated": 0.84, "angry": 0.16, "calm": 0.0},
        },
    },
    "usage": {"input_tokens": 589, "output_tokens": 212},
}

# Score request levels and response: https://docs.typesafe.ai/primitives/score
JEV_SCORE_QUESTIONS = {
    "bug_severity": {
        "type": "score",
        "criteria": [
            "Cosmetic; no impact to functionality",
            "Broken or degraded feature, but workaround exists",
            "Blocking issue; no workaround exists",
        ],
    }
}
JEV_SCORE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "bug_severity": {
            "type": "score",
            "score": 1.43,
            "confidence": 0.35,
            "legend": {
                "0": "Cosmetic; no impact to functionality",
                "1": "Broken or degraded feature, but workaround exists",
                "2": "Blocking issue; no workaround exists",
            },
            "probabilities": {"0": 0.0, "1": 0.57, "2": 0.43},
        }
    },
    "usage": {"input_tokens": 332, "output_tokens": 18},
}

# Documented result type outside this proposal: https://docs.typesafe.ai/primitives/box
JEV_BOX_QUESTIONS = {"mug": {"type": "box"}}
JEV_BOX_RESPONSE = {
    "model": "jev-1.14.0",
    "answers": {
        "mug": {
            "type": "box",
            "box": {"top": 0.25, "bottom": 0.82, "left": 0.44, "right": 0.84},
            "confidence": 0.92,
        }
    },
    "usage": {"input_tokens": 290, "output_tokens": 21},
}


def normalize_jev_response(request_questions, response):
    """Map documented Jev Noul, Choice, and Score answers to decision results.

    Iterate request questions for stable original indices and correlate the
    response's named answers by key. Request model and usage are intentionally
    left to the request-level inference attributes.
    """
    results = []
    answers = response.get("answers", {})
    for index, (name, question) in enumerate(request_questions.items()):
        answer = answers.get(name)
        if not isinstance(answer, dict) or answer.get("type") != question.get("type"):
            continue

        result = {"question_index": index, "question_name": name}
        if answer["type"] == "noul":
            result.update(type="predicate", probability=answer["noul"])
        elif answer["type"] == "choice":
            result.update(type="choice", value=answer["choice"])
            probability = answer.get("probabilities", {}).get(answer["choice"])
            if probability is not None:
                result["probability"] = probability
        elif answer["type"] == "score":
            legend = answer.get("legend", {})
            labels = [legend.get(str(level)) for level in range(len(legend))]
            if (
                len(labels) < 2
                or set(legend) != {str(level) for level in range(len(legend))}
                or any(not isinstance(label, str) for label in labels)
            ):
                continue
            result.update(type="score", value=answer["score"], levels=labels)
        else:
            # Documented Jev answer types outside this schema (for example Box)
            # are not reinterpreted as one of its decision-result variants.
            continue
        results.append(result)
    return results


class DecisionTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemorySpanExporter()
        self.traces = TracerProvider()
        self.traces.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.reader = InMemoryMetricReader()
        self.metrics = MeterProvider(metric_readers=[self.reader])
        self.log_exporter = InMemoryLogRecordExporter()
        self.logs = LoggerProvider()
        self.logs.add_log_record_processor(SimpleLogRecordProcessor(self.log_exporter))
        tracer_patch = patch.object(decisions, "reference_tracer", return_value=self.traces.get_tracer("test"))
        meter_patch = patch.object(decisions, "reference_meter", return_value=self.metrics.get_meter("test"))
        logger_patch = patch.object(decisions, "reference_event_logger", return_value=self.logs.get_logger("test"))
        tracer_patch.start()
        meter_patch.start()
        logger_patch.start()
        self.addCleanup(tracer_patch.stop)
        self.addCleanup(meter_patch.stop)
        self.addCleanup(logger_patch.stop)
        self.addCleanup(self.logs.shutdown)
        self.addCleanup(self.traces.shutdown)
        self.addCleanup(self.metrics.shutdown)

    def points(self):
        return {
            metric.name: metric.data.data_points
            for resource in self.reader.get_metrics_data().resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }

    def assert_decision_attributes(self, attributes):
        self.assertEqual(attributes["gen_ai.operation.name"], "decision")
        self.assertEqual(attributes["gen_ai.provider.name"], "openai")
        self.assertEqual(attributes["gen_ai.request.model"], "gpt-6-luna")
        self.assertEqual(attributes["gen_ai.response.model"], "gpt-6-luna")
        self.assertEqual(attributes["gen_ai.usage.input_tokens"], 42)
        self.assertEqual(attributes["gen_ai.usage.output_tokens"], 0)
        for unsupported in (
            "gen_ai.system_instructions",
            "gen_ai.tool.definitions",
            "gen_ai.request.temperature",
            "gen_ai.request.top_p",
            "gen_ai.request.top_k",
            "gen_ai.request.max_tokens",
            "gen_ai.request.choice.count",
            "gen_ai.request.frequency_penalty",
            "gen_ai.request.presence_penalty",
            "gen_ai.request.stop_sequences",
            "gen_ai.request.seed",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, attributes)

    def test_request_model_and_usage_remain_separate_from_results(self):
        input_text, questions, answers = next(decisions.decision_cases())
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client,
                model="gpt-6-luna",
                input=input_text,
                questions=questions,
                capture_results=True,
            )
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assert_decision_attributes(span.attributes)
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 42)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 0)
        self.assertNotIn("error.type", span.attributes)
        self.assertNotIn("gen_ai.response.finish_reasons", span.attributes)
        self.assertNotIn("gen_ai.request.choice.count", span.attributes)
        self.assertNotIn("gen_ai.output.messages", span.attributes)
        self.assertNotIn("gen_ai.input.messages", span.attributes)
        self.assertNotIn("gen_ai.output.type", span.attributes)
        results = json.loads(span.attributes["gen_ai.decision.results"])
        self.assertEqual(
            results,
            [{"type": "predicate", "question_index": 0, "question_name": "damaged", "probability": 0.95}],
        )
        content_models.DecisionResults.model_validate(results)
        RESULT_VALIDATOR.validate(results)
        self.assertNotIn("model", json.dumps(results))
        self.assertNotIn("usage", json.dumps(results))
        self.assertEqual(len(self.log_exporter.get_finished_logs()), 0)
        points = self.points()
        duration = points["gen_ai.client.inference.duration"][0]
        self.assertEqual(duration.count, 1)
        self.assertEqual(duration.sum, (span.end_time - span.start_time) / 1_000_000_000)
        self.assertEqual(points["gen_ai.client.inference.operation.input_tokens"][0].count, 1)
        self.assertEqual(points["gen_ai.client.inference.usage.input_tokens"][0].value, 42)
        self.assertEqual(points["gen_ai.client.inference.operation.output_tokens"][0].sum, 0)
        self.assertTrue(
            all(point.attributes["gen_ai.operation.name"] == "decision" for p in points.values() for point in p)
        )

    def test_request_error_is_rethrown_without_inventing_usage(self):
        input_text, questions, answers = next(decisions.decision_cases())
        with (
            decisions.mock_decision_client(input_text, questions, answers, status_code=400) as client,
            self.assertRaises(BadRequestError),
        ):
            decisions.decision_request(client, model="gpt-6-luna", input=input_text, questions=questions)
        (span,) = self.exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], "BadRequestError")
        self.assertFalse(any(key.startswith("gen_ai.usage.") for key in span.attributes))
        self.assertNotIn("gen_ai.decision.results", span.attributes)
        points = self.points()
        self.assertEqual(set(points), {"gen_ai.client.inference.duration"})
        self.assertEqual(points["gen_ai.client.inference.duration"][0].attributes["error.type"], "BadRequestError")
        (record,) = self.log_exporter.get_finished_logs()
        event = record.log_record
        self.assertEqual(event.event_name, "gen_ai.client.operation.exception")
        self.assertEqual(event.severity_number, SeverityNumber.WARN)
        self.assertEqual(event.trace_id, span.context.trace_id)
        self.assertEqual(event.span_id, span.context.span_id)
        self.assertEqual(event.attributes["exception.type"], "BadRequestError")
        self.assertEqual(event.attributes["gen_ai.operation.name"], "decision")
        self.assertNotIn("gen_ai.decision.results", event.attributes)
        self.assertFalse(any(key.startswith("gen_ai.usage.") for key in event.attributes))

    def test_documented_predicate_response_is_exported_and_validated(self):
        for input_text, questions, answers in decisions.decision_cases():
            with decisions.mock_decision_client(input_text, questions, answers) as client:
                decisions.decision_request(
                    client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
                )
        for span in self.exporter.get_finished_spans():
            self.assert_decision_attributes(span.attributes)
        results = [
            json.loads(span.attributes["gen_ai.decision.results"]) for span in self.exporter.get_finished_spans()
        ]
        for result in results:
            content_models.DecisionResults.model_validate(result)
            RESULT_VALIDATOR.validate(result)
        self.assertEqual(
            results[0],
            [{"type": "predicate", "question_index": 0, "question_name": "damaged", "probability": 0.95}],
        )
        for metric in self.points().values():
            for point in metric:
                self.assertNotIn("gen_ai.decision.results", point.attributes)
        self.assertNotIn("confidence", json.dumps(results))
        self.assertNotIn("probabilities", json.dumps(results))

    def test_documented_openai_choice_and_score_excerpts_map_to_schema(self):
        choice = AnswerAnswerResourceChoice.model_validate(OPENAI_CHOICE_ANSWER)
        choice_result = decisions.openai_decision_results([OPENAI_CHOICE_QUESTION], [choice])
        self.assertEqual(
            choice_result,
            [
                {
                    "type": "choice",
                    "question_index": 0,
                    "question_name": "department",
                    "value": "billing",
                    "probability": 0.95,
                }
            ],
        )

        score = AnswerAnswerResourceScore.model_validate(OPENAI_SCORE_ANSWER)
        score_result = decisions.openai_decision_results([OPENAI_SCORE_QUESTION], [score])
        self.assertEqual(
            score_result,
            [
                {
                    "type": "score",
                    "question_index": 0,
                    "question_name": "severity",
                    "value": 1.1,
                    "levels": ["Cosmetic", "Workaround available", "Fully blocked"],
                }
            ],
        )
        self.assertEqual(score_result[0]["levels"], [level["label"] for level in OPENAI_SCORE_QUESTION["levels"]])

        for result in (choice_result, score_result):
            content_models.DecisionResults.model_validate(result)
            RESULT_VALIDATOR.validate(result)
            self.assertNotIn("confidence", json.dumps(result))
            self.assertNotIn("probabilities", json.dumps(result))

    def test_documented_openai_refusal_contract_shape_maps_to_schema(self):
        refusal = AnswerAnswerResourceRefusal.model_validate(OPENAI_REFUSAL_ANSWER)
        result = decisions.openai_decision_results([OPENAI_CHOICE_QUESTION], [refusal])
        self.assertEqual(result, [{"type": "refusal", "question_index": 0, "question_name": "department"}])
        content_models.DecisionResults.model_validate(result)
        RESULT_VALIDATOR.validate(result)

    def test_event_results_are_structured_and_correlated_to_inference(self):
        input_text, questions, answers = next(decisions.decision_cases())
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client,
                model="gpt-6-luna",
                input=input_text,
                questions=questions,
                capture_results=True,
                results_on_event=True,
            )
        (span,) = self.exporter.get_finished_spans()
        (record,) = self.log_exporter.get_finished_logs()
        event = record.log_record
        self.assertEqual(event.event_name, "gen_ai.client.inference.operation.details")
        self.assert_decision_attributes(span.attributes)
        self.assert_decision_attributes(event.attributes)
        self.assertEqual(event.trace_id, span.context.trace_id)
        self.assertEqual(event.span_id, span.context.span_id)
        self.assertNotIn("gen_ai.decision.results", span.attributes)
        # The SDK freezes arrays as tuples; validate their JSON representation.
        event_results = json.loads(json.dumps(event.attributes["gen_ai.decision.results"]))
        content_models.DecisionResults.model_validate(event_results)
        RESULT_VALIDATOR.validate(event_results)
        self.assertEqual(
            event.attributes["gen_ai.decision.results"][0],
            {"type": "predicate", "question_index": 0, "question_name": "damaged", "probability": 0.95},
        )
        self.assertEqual(event.attributes["gen_ai.usage.input_tokens"], 42)
        self.assertEqual(event.attributes["gen_ai.usage.output_tokens"], 0)
        for metric in self.points().values():
            for point in metric:
                self.assertFalse(any(key.startswith("gen_ai.usage.") for key in point.attributes))

    def test_event_destination_does_not_enable_result_capture(self):
        input_text, questions, answers = next(decisions.decision_cases())
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client, model="gpt-6-luna", input=input_text, questions=questions, results_on_event=True
            )
        (span,) = self.exporter.get_finished_spans()
        self.assert_decision_attributes(span.attributes)
        self.assertNotIn("gen_ai.decision.results", span.attributes)
        self.assertEqual(len(self.log_exporter.get_finished_logs()), 0)

    def test_schema_rejects_ambiguous_or_invalid_results(self):
        invalid = [
            {"type": "predicate", "question_index": 0, "probability": 1.1},
            {"type": "choice", "question_index": 0, "value": 1},
            {"type": "score", "question_index": 0, "value": 0.8},
            {"type": "refusal", "question_index": -1},
            {"type": "refusal", "question_index": 0, "value": "abstain"},
            {"type": "abstain", "question_index": 0},
            {"type": "choice", "question_index": 0, "value": "technical", "confidence": 0.8},
        ]
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(ValueError):
                content_models.DecisionResults.model_validate([result])
            with self.subTest(json_schema=result), self.assertRaises(ValidationError):
                RESULT_VALIDATOR.validate([result])
        # Cross-field constraints are checked by the companion model, since JSON
        # Schema cannot compute a maximum from another property's array length.
        with self.assertRaises(ValueError):
            content_models.DecisionResults.model_validate(
                [{"type": "score", "question_index": 0, "value": 2, "levels": ["low", "high"]}]
            )
        with self.assertRaises(ValueError):
            content_models.DecisionResults.model_validate(
                [
                    {"type": "refusal", "question_index": 0},
                    {"type": "refusal", "question_index": 0},
                ]
            )

    def test_unknown_answers_are_omitted_without_renumbering(self):
        _, documented_questions, documented_answers = next(decisions.decision_cases())
        questions = [{"type": "choice", "name": "future"}, documented_questions[0]]
        answers = [
            SimpleNamespace(type="future_answer", name="future"),
            AnswerAnswerResourcePredicate.model_validate(documented_answers[0]),
        ]
        result = decisions.openai_decision_results(questions, answers)
        self.assertEqual(
            result,
            [{"type": "predicate", "question_index": 1, "question_name": "damaged", "probability": 0.95}],
        )
        content_models.DecisionResults.model_validate(result)
        RESULT_VALIDATOR.validate(result)

    def test_score_preserves_larger_scale_and_is_omitted_without_labels(self):
        answer = AnswerAnswerResourceScore.model_validate(OPENAI_SCORE_ANSWER)
        questions = [OPENAI_SCORE_QUESTION]
        result = decisions.openai_decision_results(questions, [answer])
        self.assertEqual(result[0]["value"], 1.1)
        self.assertEqual(result[0]["levels"], ["Cosmetic", "Workaround available", "Fully blocked"])
        content_models.DecisionResults.model_validate(result)
        RESULT_VALIDATOR.validate(result)
        # A malformed request context is a defensive omission test, not a
        # provider response fixture.
        questions[0]["levels"][1] = {}
        self.assertEqual(decisions.openai_decision_results(questions, [answer]), [])

    def test_missing_answers_do_not_create_abstention(self):
        input_text, questions, _ = next(decisions.decision_cases())
        with decisions.mock_decision_client(input_text, questions, []) as client:
            decisions.decision_request(
                client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
            )
        (span,) = self.exporter.get_finished_spans()
        self.assertNotIn("gen_ai.decision.results", span.attributes)
        self.assertEqual(span.status.status_code, StatusCode.UNSET)

    def test_generated_schema_matches_source_and_is_valid(self):
        Draft202012Validator.check_schema(RESULT_SCHEMA)
        self.assertEqual(RESULT_SCHEMA, content_models.DecisionResults.model_json_schema())

    def test_jev_documented_responses_map_to_valid_results(self):
        cases = (
            (JEV_NOUL_QUESTIONS, JEV_NOUL_RESPONSE),
            (JEV_CHOICE_QUESTIONS, JEV_CHOICE_RESPONSE),
            (JEV_SCORE_QUESTIONS, JEV_SCORE_RESPONSE),
        )
        all_results = []
        for questions, response in cases:
            # Provider wire envelopes contain provider fields that the telemetry
            # result schema intentionally does not model.
            with self.assertRaises(ValidationError):
                RESULT_VALIDATOR.validate(response)
            results = normalize_jev_response(questions, response)
            content_models.DecisionResults.model_validate(results)
            RESULT_VALIDATOR.validate(results)
            all_results.extend(results)
            self.assertNotIn("model", json.dumps(results))
            self.assertNotIn("usage", json.dumps(results))
            self.assertNotIn("confidence", json.dumps(results))
            self.assertNotIn("probabilities", json.dumps(results))

        self.assertEqual(
            all_results[:2],
            [
                {
                    "type": "predicate",
                    "question_index": 0,
                    "question_name": "is_human_escalation",
                    "probability": 0.99,
                },
                {
                    "type": "predicate",
                    "question_index": 1,
                    "question_name": "is_repeat_contact",
                    "probability": 0.93,
                },
            ],
        )
        choice_results = all_results[2:7]
        self.assertEqual(
            [(r["question_index"], r["question_name"], r["value"], r["probability"]) for r in choice_results],
            [
                (0, "department", "returns", 0.61),
                (1, "return_reason", "wrong_size", 1.0),
                (2, "shipping_issue", "delayed", 0.74),
                (3, "requested_resolution", "refund", 0.4),
                (4, "tone", "frustrated", 0.84),
            ],
        )
        self.assertEqual(
            all_results[7],
            {
                "type": "score",
                "question_index": 0,
                "question_name": "bug_severity",
                "value": 1.43,
                "levels": [
                    "Cosmetic; no impact to functionality",
                    "Broken or degraded feature, but workaround exists",
                    "Blocking issue; no workaround exists",
                ],
            },
        )
        self.assertEqual(all_results[7]["levels"], JEV_SCORE_QUESTIONS["bug_severity"]["criteria"])

        # Model and usage appear in each provider response envelope and stay at
        # request scope; they are not copied into individual result objects.
        self.assertEqual(JEV_NOUL_RESPONSE["model"], "jev-1.13.0")
        self.assertEqual(JEV_NOUL_RESPONSE["usage"], {"input_tokens": 360, "output_tokens": 39})
        self.assertEqual(JEV_CHOICE_RESPONSE["usage"], {"input_tokens": 589, "output_tokens": 212})
        self.assertEqual(JEV_SCORE_RESPONSE["usage"], {"input_tokens": 332, "output_tokens": 18})

    def test_jev_box_is_a_documented_coverage_gap(self):
        self.assertEqual(normalize_jev_response(JEV_BOX_QUESTIONS, JEV_BOX_RESPONSE), [])


if __name__ == "__main__":
    unittest.main()
