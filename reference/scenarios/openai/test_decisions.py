"""Check request-scoped telemetry using real SDK calls and in-memory exporters."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import scenario as decisions
from jsonschema import Draft202012Validator, ValidationError
from openai import BadRequestError
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

    def test_multiple_answers_and_refusal_do_not_multiply_usage(self):
        input_text, questions, answers = list(decisions.decision_cases())[-1]
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            result = decisions.decision_request(client, model="gpt-6-luna", input=input_text, questions=questions)
        self.assertEqual([answer.type for answer in result.answers], ["choice", "refusal"])
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
        self.assertNotIn("gen_ai.decision.results", span.attributes)
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

    def test_result_variants_are_exported_with_question_correlation(self):
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
            [
                {
                    "type": "choice",
                    "question_index": 0,
                    "question_name": "department",
                    "value": "technical",
                    "probability": 0.72,
                }
            ],
        )
        self.assertEqual(results[1][0]["value"], 0.84)
        self.assertEqual(results[1][0]["levels"], ["irrelevant", "relevant"])
        self.assertEqual(results[2][0], {"type": "predicate", "question_index": 0, "probability": 0.87})
        self.assertIs(results[2][1]["value"], True)
        self.assertEqual(results[2][1]["probability"], 0.87)
        self.assertEqual(results[3][1], {"type": "refusal", "question_index": 1, "question_name": "urgent"})
        for metric in self.points().values():
            for point in metric:
                self.assertNotIn("gen_ai.decision.results", point.attributes)
        self.assertNotIn("confidence", json.dumps(results))
        self.assertNotIn("probabilities", json.dumps(results))

    def test_event_results_are_structured_and_correlated_to_inference(self):
        input_text, questions, answers = list(decisions.decision_cases())[-1]
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
        self.assertEqual(event.attributes["gen_ai.decision.results"][1]["type"], "refusal")
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
        input_text, questions, answers = list(decisions.decision_cases())[-1]
        answers[0] = {"type": "future_answer", "name": "department"}
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
            )
        (span,) = self.exporter.get_finished_spans()
        self.assertEqual(
            json.loads(span.attributes["gen_ai.decision.results"]),
            [{"type": "refusal", "question_index": 1, "question_name": "urgent"}],
        )

    def test_score_preserves_larger_scale_and_is_omitted_without_labels(self):
        input_text, questions, answers = list(decisions.decision_cases())[1]
        questions[0]["levels"] = [{"label": label} for label in ["irrelevant", "partial", "relevant"]]
        answers[0]["score"] = 1.68
        answers[0]["probabilities"] = [
            {"value": 0, "label": "irrelevant", "probability": 0.16},
            {"value": 1, "label": "partial", "probability": 0},
            {"value": 2, "label": "relevant", "probability": 0.84},
        ]
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
            )
        result = json.loads(self.exporter.get_finished_spans()[0].attributes["gen_ai.decision.results"])[0]
        self.assertEqual(result["value"], 1.68)
        self.assertEqual(result["levels"], ["irrelevant", "partial", "relevant"])
        content_models.DecisionResults.model_validate([result])
        RESULT_VALIDATOR.validate([result])
        # Exercise defensive omission when a request level cannot be captured.
        # This malformed fixture is not an example of an accepted provider request.
        questions[0]["levels"][1] = {}
        with decisions.mock_decision_client(input_text, questions, answers) as client:
            decisions.decision_request(
                client, model="gpt-6-luna", input=input_text, questions=questions, capture_results=True
            )
        self.assertNotIn("gen_ai.decision.results", self.exporter.get_finished_spans()[1].attributes)

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


if __name__ == "__main__":
    unittest.main()
