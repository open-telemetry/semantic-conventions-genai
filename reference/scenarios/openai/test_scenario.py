"""Check inference exception telemetry through the real OpenAI SDK."""

import json
import os
import unittest
from unittest.mock import patch

import httpx2
import openai
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class InferenceExceptionTests(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.addCleanup(self.tracer_provider.shutdown)
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        self.log_exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.addCleanup(self.logger_provider.shutdown)
        self.logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.log_exporter))
        for attribute, value in (
            ("_reference_tracer", self.tracer_provider.get_tracer("test")),
            ("reference_event_logger", lambda: self.logger_provider.get_logger("test")),
        ):
            patcher = patch.object(scenario, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def client(self, handler, *, max_retries=0):
        client = openai.OpenAI(
            base_url=scenario.MOCK_BASE_URL,
            api_key="mock-key",
            max_retries=max_retries,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        return client

    def assert_exception_telemetry(self, error):
        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.attributes["gen_ai.operation.name"], "chat")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, str(error))
        self.assertEqual(span.events, ())

        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        event = logs[0].log_record
        self.assertEqual(event.event_name, "gen_ai.client.inference.exception")
        self.assertEqual(event.severity_number, SeverityNumber.WARN)
        self.assertEqual(event.severity_number.value, 13)
        self.assertEqual(event.trace_id, span.context.trace_id)
        self.assertEqual(event.span_id, span.context.span_id)
        self.assertEqual(event.attributes["exception.type"], f"{type(error).__module__}.{type(error).__qualname__}")
        self.assertEqual(event.attributes["exception.message"], str(error))
        self.assertIn("Traceback (most recent call last)", event.attributes["exception.stacktrace"])
        self.assertIn(type(error).__qualname__, event.attributes["exception.stacktrace"])
        self.assertIn(str(error), event.attributes["exception.stacktrace"])
        self.assertEqual(
            set(event.attributes),
            {"exception.type", "exception.message", "exception.stacktrace"},
        )
        self.assertEqual(span.attributes["error.type"], event.attributes["exception.type"])

    def test_rate_limit_uses_actual_sdk_exception(self):
        def respond(request):
            self.assertEqual(request.url.path, "/v1/chat/completions")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-4o-mini")
            self.assertEqual(body["messages"][-1]["content"], "Say hello.")
            return httpx2.Response(
                429,
                json={"error": {"message": "Slow down", "type": "rate_limit_error", "code": "rate_limit_exceeded"}},
            )

        with self.assertRaises(openai.RateLimitError) as caught:
            scenario.run_chat_reference(self.client(respond))
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn("Slow down", str(caught.exception))
        self.assert_exception_telemetry(caught.exception)

    def assert_success_telemetry(self):
        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertNotIn("error.type", span.attributes)
        self.assertEqual(span.events, ())
        self.assertEqual(
            [log.log_record.event_name for log in self.log_exporter.get_finished_logs()],
            ["gen_ai.client.inference.operation.details"],
        )

    def success_response(self):
        return httpx2.Response(
            200,
            json={
                "id": "chatcmpl-success",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {"index": index, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hello"}}
                    for index in range(2)
                ],
            },
        )

    def test_success_emits_no_exception(self):
        scenario.run_chat_reference(self.client(lambda request: self.success_response()))
        self.assert_success_telemetry()

    def test_successful_retry_emits_no_exception(self):
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

        scenario.run_chat_reference(self.client(respond, max_retries=1))
        self.assertEqual(len(requests), 2)
        self.assert_success_telemetry()


if __name__ == "__main__":
    unittest.main()
