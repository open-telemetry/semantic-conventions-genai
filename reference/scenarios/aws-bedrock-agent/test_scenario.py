"""Check exception events across the client invoke-agent span."""

import os
import unittest
from unittest.mock import Mock, patch

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class InvokeAgentExceptionTests(unittest.TestCase):
    def setUp(self):
        self.spans = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        self.addCleanup(tracer_provider.shutdown)
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.logs = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        self.addCleanup(logger_provider.shutdown)
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.logs))
        tracer_patch = patch.object(scenario, "tracer", tracer_provider.get_tracer("test"))
        tracer_patch.start()
        self.addCleanup(tracer_patch.stop)
        logger_patch = patch.object(scenario, "reference_event_logger", return_value=logger_provider.get_logger("test"))
        logger_patch.start()
        self.addCleanup(logger_patch.stop)

        self.client = Mock()
        self.client.invoke_agent.return_value = {"completion": [{"chunk": {"bytes": b"Hello"}}]}

    def assert_invocation_failure(self, error):
        with self.assertRaises(type(error)) as raised:
            scenario.run_invoke_agent(self.client, "agent-id")
        self.assertIs(raised.exception, error)
        (span,) = self.spans.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], f"{type(error).__module__}.{type(error).__qualname__}")
        self.assertEqual(span.events, ())
        logs = self.logs.get_finished_logs()
        self.assertEqual(len(logs), 1)
        record = logs[0].log_record
        self.assertEqual(record.event_name, "gen_ai.client.invoke_agent.exception")
        self.assertEqual(record.severity_number, SeverityNumber.WARN)
        self.assertEqual(record.attributes["exception.message"], str(error))
        self.assertEqual(record.trace_id, span.context.trace_id)
        self.assertEqual(record.span_id, span.context.span_id)

    def test_sdk_failure_emits_one_event(self):
        error = RuntimeError("SDK call failed")
        self.client.invoke_agent.side_effect = error
        self.assert_invocation_failure(error)

    def test_stream_failure_emits_one_event(self):
        error = RuntimeError("Stream failed")

        def completion():
            yield {"chunk": {"bytes": b"partial"}}
            raise error

        self.client.invoke_agent.return_value = {"completion": completion()}
        self.assert_invocation_failure(error)

    def test_chunk_processing_failure_emits_one_event(self):
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
        chunk_bytes = Mock()
        chunk_bytes.decode.side_effect = error
        self.client.invoke_agent.return_value = {"completion": [{"chunk": {"bytes": chunk_bytes}}]}
        self.assert_invocation_failure(error)

    def test_usage_processing_failure_emits_one_event(self):
        error = RuntimeError("Cannot read trace usage")
        trace = Mock()
        trace.get.side_effect = error
        self.client.invoke_agent.return_value = {"completion": [{"trace": trace}]}
        self.assert_invocation_failure(error)

    def test_success_records_output_and_emits_no_exception_event(self):
        scenario.run_invoke_agent(self.client, "agent-id")
        self.assertEqual(self.logs.get_finished_logs(), ())
        (span,) = self.spans.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertIn("Hello", span.attributes["gen_ai.output.messages"])


if __name__ == "__main__":
    unittest.main()
