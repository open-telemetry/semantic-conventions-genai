"""Check request-scoped telemetry using real SDK calls and in-memory exporters."""

import unittest
from unittest.mock import patch

import decisions
from openai import BadRequestError
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode


class DecisionTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemorySpanExporter()
        self.traces = TracerProvider()
        self.traces.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.reader = InMemoryMetricReader()
        self.metrics = MeterProvider(metric_readers=[self.reader])
        tracer_patch = patch.object(decisions, "reference_tracer", return_value=self.traces.get_tracer("test"))
        meter_patch = patch.object(decisions, "reference_meter", return_value=self.metrics.get_meter("test"))
        tracer_patch.start()
        meter_patch.start()
        self.addCleanup(tracer_patch.stop)
        self.addCleanup(meter_patch.stop)
        self.addCleanup(self.traces.shutdown)
        self.addCleanup(self.metrics.shutdown)

    def points(self):
        return {
            metric.name: metric.data.data_points
            for resource in self.reader.get_metrics_data().resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }

    def test_multiple_answers_and_refusal_do_not_multiply_usage(self):
        input_text, questions, answers = list(decisions.cases())[-1]
        with decisions.mock_client(input_text, questions, answers) as client:
            result = decisions.decision_request(client, model="gpt-6-luna", input=input_text, questions=questions)
        self.assertEqual([answer.type for answer in result.answers], ["choice", "refusal"])
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 42)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 0)
        self.assertNotIn("error.type", span.attributes)
        self.assertNotIn("gen_ai.response.finish_reasons", span.attributes)
        self.assertNotIn("gen_ai.request.choice.count", span.attributes)
        self.assertNotIn("gen_ai.output.messages", span.attributes)
        self.assertNotIn("gen_ai.input.messages", span.attributes)
        self.assertNotIn("gen_ai.output.type", span.attributes)
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
        input_text, questions, answers = next(decisions.cases())
        with (
            decisions.mock_client(input_text, questions, answers, status_code=400) as client,
            self.assertRaises(BadRequestError),
        ):
            decisions.decision_request(client, model="gpt-6-luna", input=input_text, questions=questions)
        (span,) = self.exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], "BadRequestError")
        self.assertFalse(any(key.startswith("gen_ai.usage.") for key in span.attributes))
        points = self.points()
        self.assertEqual(set(points), {"gen_ai.client.inference.duration"})
        self.assertEqual(points["gen_ai.client.inference.duration"][0].attributes["error.type"], "BadRequestError")


if __name__ == "__main__":
    unittest.main()
