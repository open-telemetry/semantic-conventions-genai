"""Check embeddings exception telemetry from the real OpenAI SDK."""

import os
import unittest
from unittest.mock import patch

import httpx2
import openai
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class EmbeddingsExceptionTests(unittest.TestCase):
    def setUp(self):
        self.spans = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.addCleanup(tracer_provider.shutdown)

        self.logs = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.logs))
        self.addCleanup(logger_provider.shutdown)

        self.metrics = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[self.metrics])
        self.addCleanup(meter_provider.shutdown)
        meter = meter_provider.get_meter("test")

        self.enterContext(patch.object(scenario, "_reference_tracer", tracer_provider.get_tracer("test")))
        self.enterContext(
            patch.object(scenario, "reference_event_logger", return_value=logger_provider.get_logger("test"))
        )
        self.enterContext(
            patch.object(scenario, "_embeddings_duration", meter.create_histogram("gen_ai.client.embeddings.duration"))
        )
        self.enterContext(
            patch.object(
                scenario,
                "_embeddings_input_tokens",
                meter.create_histogram("gen_ai.client.embeddings.operation.input_tokens"),
            )
        )

    def run_embeddings(self, handler, *, max_retries=0):
        with openai.OpenAI(
            base_url=scenario.MOCK_BASE_URL,
            api_key="mock-key",
            max_retries=max_retries,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        ) as client:
            scenario.run_embeddings_reference(client)

    def recorded_metrics(self):
        return {
            metric.name: metric.data.data_points[0]
            for resource in self.metrics.get_metrics_data().resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }

    @staticmethod
    def success_response():
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.25, 0.5]}],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    def test_sdk_error_records_one_correlated_exception_log(self):
        with self.assertRaises(openai.BadRequestError) as raised:
            self.run_embeddings(
                lambda request: httpx2.Response(
                    400,
                    json={
                        "error": {"message": "Invalid input", "type": "invalid_request_error", "code": "invalid_input"}
                    },
                )
            )

        exception = raised.exception
        self.assertEqual(exception.code, "invalid_input")
        self.assertEqual(len(self.spans.get_finished_spans()), 1)
        span = self.spans.get_finished_spans()[0]
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, str(exception))
        self.assertEqual(span.attributes["error.type"], type(exception).__qualname__)
        self.assertEqual(span.events, ())

        self.assertEqual(len(self.logs.get_finished_logs()), 1)
        record = self.logs.get_finished_logs()[0].log_record
        self.assertEqual(record.event_name, "gen_ai.client.embeddings.exception")
        self.assertEqual(record.severity_number, SeverityNumber.WARN)
        self.assertEqual(record.severity_number.value, 13)
        self.assertEqual(record.trace_id, span.context.trace_id)
        self.assertEqual(record.span_id, span.context.span_id)
        self.assertGreaterEqual(record.observed_timestamp, span.start_time)
        self.assertLessEqual(record.observed_timestamp, span.end_time)
        self.assertEqual(set(record.attributes), {"exception.type", "exception.message", "exception.stacktrace"})
        self.assertEqual(
            record.attributes["exception.type"], f"{type(exception).__module__}.{type(exception).__qualname__}"
        )
        self.assertEqual(record.attributes["exception.message"], str(exception))
        self.assertIn("run_embeddings_reference", record.attributes["exception.stacktrace"])
        self.assertIn("Traceback (most recent call last):", record.attributes["exception.stacktrace"])
        self.assertTrue(record.attributes["exception.stacktrace"].endswith(f"openai.BadRequestError: {exception}\n"))

        metrics = self.recorded_metrics()
        self.assertEqual(
            set(metrics), {"gen_ai.client.embeddings.duration", "gen_ai.client.embeddings.operation.input_tokens"}
        )
        for point in metrics.values():
            self.assertEqual(point.count, 1)
            self.assertEqual(point.attributes["error.type"], span.attributes["error.type"])
        self.assertGreater(metrics["gen_ai.client.embeddings.duration"].sum, 0)
        self.assertEqual(metrics["gen_ai.client.embeddings.operation.input_tokens"].sum, 0)

    def test_error_reference_emits_the_embeddings_event(self):
        scenario.run_embeddings_error_reference()

        self.assertEqual(len(self.logs.get_finished_logs()), 1)
        self.assertEqual(self.logs.get_finished_logs()[0].log_record.event_name, "gen_ai.client.embeddings.exception")

    def test_success_records_no_exception(self):
        self.run_embeddings(lambda request: self.success_response())

        self.assert_success()

    def test_successful_sdk_retry_records_no_exception(self):
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx2.Response(
                    429,
                    headers={"retry-after-ms": "1"},
                    json={"error": {"message": "Try again", "type": "rate_limit_error"}},
                )
            return self.success_response()

        self.run_embeddings(respond, max_retries=1)

        self.assertEqual(len(requests), 2)
        self.assert_success()

    def test_exhausted_sdk_retries_record_only_the_terminal_exception(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx2.Response(
                429,
                headers={"retry-after-ms": "1"},
                json={"error": {"message": "Try again", "type": "rate_limit_error"}},
            )

        with self.assertRaises(openai.RateLimitError):
            self.run_embeddings(respond, max_retries=1)

        self.assertEqual(len(requests), 2)
        self.assertEqual(len(self.spans.get_finished_spans()), 1)
        self.assertEqual(len(self.logs.get_finished_logs()), 1)
        record = self.logs.get_finished_logs()[0].log_record
        self.assertEqual(record.event_name, "gen_ai.client.embeddings.exception")
        self.assertEqual(record.attributes["exception.type"], "openai.RateLimitError")
        self.assertEqual(self.recorded_metrics()["gen_ai.client.embeddings.duration"].count, 1)

    def assert_success(self):
        self.assertEqual(self.logs.get_finished_logs(), ())
        self.assertEqual(len(self.spans.get_finished_spans()), 1)
        span = self.spans.get_finished_spans()[0]
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertNotIn("error.type", span.attributes)
        self.assertEqual(span.events, ())
        metrics = self.recorded_metrics()
        for point in metrics.values():
            self.assertEqual(point.count, 1)
            self.assertNotIn("error.type", point.attributes)
        self.assertEqual(metrics["gen_ai.client.embeddings.operation.input_tokens"].sum, 4)


if __name__ == "__main__":
    unittest.main()
