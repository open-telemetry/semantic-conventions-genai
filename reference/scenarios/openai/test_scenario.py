"""Check fetch-response exception scope and successful fetch telemetry."""

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
from opentelemetry.trace import StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class FetchResponseTests(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        self.addCleanup(tracer_provider.shutdown)
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        self.log_exporter = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        self.addCleanup(logger_provider.shutdown)
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.log_exporter))
        tracer_patch = patch.object(scenario, "_reference_tracer", tracer_provider.get_tracer("test"))
        tracer_patch.start()
        self.addCleanup(tracer_patch.stop)
        logger_patch = patch.object(scenario, "reference_event_logger", return_value=logger_provider.get_logger("test"))
        logger_patch.start()
        self.addCleanup(logger_patch.stop)

    def response_payload(self, **overrides):
        return {
            "id": "resp-fetch",
            "object": "response",
            "created_at": 0,
            "model": "gpt-4o-mini",
            "status": "completed",
            "instructions": "Be helpful.",
            "service_tier": "default",
            "output": [
                {
                    "id": "message-fetch",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "Hello.", "annotations": []}],
                }
            ],
            **overrides,
        }

    def client(self, response):
        client = openai.OpenAI(
            base_url=scenario.MOCK_BASE_URL,
            api_key="mock-key",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(lambda request: response)),
        )
        self.addCleanup(client.close)
        return client

    def assert_fetch_exception(self, error):
        span = self.span_exporter.get_finished_spans()[-1]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], type(error).__qualname__)
        self.assertEqual(span.status.description, f"{type(error).__name__}: {error}")
        self.assertEqual(span.events, ())
        record = self.log_exporter.get_finished_logs()[-1].log_record
        self.assertEqual(record.event_name, "gen_ai.client.fetch_response.exception")
        self.assertEqual(record.severity_number, SeverityNumber.WARN)
        self.assertEqual(
            record.attributes["exception.type"],
            type(error).__qualname__
            if type(error).__module__ == "builtins"
            else f"{type(error).__module__}.{type(error).__qualname__}",
        )
        self.assertEqual(record.attributes["exception.message"], str(error))
        self.assertEqual(record.trace_id, span.context.trace_id)
        self.assertEqual(record.span_id, span.context.span_id)
        self.assertIn(str(error), record.attributes["exception.stacktrace"])

    def test_retrieve_exception(self):
        client = self.client(httpx2.Response(404, json={"error": {"message": "Response not found"}}))
        with self.assertRaises(openai.NotFoundError) as raised:
            scenario._emit_fetch_response_span(client, "resp-missing")
        self.assert_fetch_exception(raised.exception)
        self.assertEqual(len(self.log_exporter.get_finished_logs()), 1)

    def test_stream_iteration_exception(self):
        error = RuntimeError("Stream interrupted")

        def stream():
            event = {"type": "response.completed", "sequence_number": 2, "response": self.response_payload()}
            yield f"event: response.completed\ndata: {json.dumps(event)}\n\n".encode()
            raise error

        client = self.client(httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=stream()))
        with self.assertRaises(RuntimeError) as raised:
            scenario._emit_fetch_response_span(client, "resp-fetch", starting_after=1)
        self.assertIs(raised.exception, error)
        self.assert_fetch_exception(error)

    def test_stream_without_response_records_processing_exception(self):
        client = self.client(
            httpx2.Response(200, headers={"content-type": "text/event-stream"}, content="data: [DONE]\n\n")
        )
        with self.assertRaises(AttributeError) as raised:
            scenario._emit_fetch_response_span(client, "resp-fetch", starting_after=1)
        self.assert_fetch_exception(raised.exception)
        self.assertEqual(len(self.log_exporter.get_finished_logs()), 1)

    def test_response_processing_exceptions(self):
        for helper in ("responses_finish_reason", "responses_output_messages"):
            with self.subTest(helper=helper):
                client = self.client(httpx2.Response(200, json=self.response_payload()))
                error = RuntimeError(f"{helper} failed")
                with patch.object(scenario, helper, side_effect=error), self.assertRaises(RuntimeError) as raised:
                    scenario._emit_fetch_response_span(client, "resp-fetch")
                self.assertIs(raised.exception, error)
                self.assert_fetch_exception(error)
        self.assertEqual(len(self.log_exporter.get_finished_logs()), 2)

    def test_successful_fetch_preserves_generation_outcome(self):
        for status, finish_reason in (
            ("completed", "stop"),
            ("failed", "error"),
            ("incomplete", "length"),
            ("queued", None),
            ("in_progress", None),
        ):
            for streaming in (False, True):
                with self.subTest(status=status, streaming=streaming):
                    payload = self.response_payload(
                        status=status,
                        incomplete_details={"reason": "max_output_tokens"} if status == "incomplete" else None,
                    )
                    if streaming:
                        event = {"type": f"response.{status}", "sequence_number": 2, "response": payload}
                        response = httpx2.Response(
                            200,
                            headers={"content-type": "text/event-stream"},
                            content=f"event: response.{status}\ndata: {json.dumps(event)}\n\n",
                        )
                    else:
                        response = httpx2.Response(200, json=payload)
                    scenario._emit_fetch_response_span(
                        self.client(response), "resp-fetch", starting_after=1 if streaming else None
                    )
                    span = self.span_exporter.get_finished_spans()[-1]
                    self.assertEqual(span.status.status_code, StatusCode.UNSET)
                    self.assertNotIn("error.type", span.attributes)
                    self.assertEqual(span.attributes["gen_ai.response.id"], "resp-fetch")
                    self.assertEqual(span.attributes["gen_ai.response.model"], "gpt-4o-mini")
                    self.assertEqual(span.attributes["gen_ai.response.status"], status)
                    self.assertEqual(
                        span.attributes.get("gen_ai.response.finish_reasons"),
                        (finish_reason,) if finish_reason else None,
                    )
                    self.assertEqual(span.attributes.get("gen_ai.request.stream_cursor"), "1" if streaming else None)
                    self.assertEqual(span.attributes["openai.response.service_tier"], "default")
                    self.assertEqual(
                        json.loads(span.attributes["gen_ai.system_instructions"]),
                        [{"type": "text", "content": "Be helpful."}],
                    )
                    self.assertEqual(
                        json.loads(span.attributes["gen_ai.output.messages"]),
                        [{"role": "assistant", "parts": [{"type": "text", "content": "Hello."}]}],
                    )
                    self.assertFalse(any(name.startswith("gen_ai.usage.") for name in span.attributes))
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 10)
        self.assertEqual(self.log_exporter.get_finished_logs(), ())


if __name__ == "__main__":
    unittest.main()
