"""Check exception events across the client invoke-agent span."""

import os
import unittest
from types import SimpleNamespace
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
        self.client.agents.create_version.return_value = SimpleNamespace(id="agent-id", name="agent", version="1")
        self.openai_client = self.client.get_openai_client.return_value
        self.response = SimpleNamespace(
            id="response-id",
            output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="Hello")])],
            status="completed",
            usage=None,
        )
        self.openai_client.responses.create.return_value = self.response

    def assert_invocation_failure(self, error):
        with self.assertRaises(type(error)) as raised:
            scenario.run_invoke_agent(self.client)
        self.assertIs(raised.exception, error)
        span = self.spans.get_finished_spans()[-1]
        self.assertEqual(span.attributes["gen_ai.operation.name"], "invoke_agent")
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
        self.openai_client.close.assert_called_once_with()

    def test_sdk_failure_emits_one_event_and_closes_client(self):
        error = RuntimeError("SDK call failed")
        self.openai_client.responses.create.side_effect = error
        self.assert_invocation_failure(error)

    def test_response_processing_failure_emits_one_event_and_closes_client(self):
        error = RuntimeError("Cannot read agent output")
        response = Mock()
        type(response).output = property(Mock(side_effect=error))
        self.openai_client.responses.create.return_value = response
        self.assert_invocation_failure(error)

    def test_usage_processing_failure_emits_one_event_and_closes_client(self):
        error = RuntimeError("Cannot read usage")
        usage = Mock()
        type(usage).input_tokens = property(Mock(side_effect=error))
        self.response.usage = usage
        self.assert_invocation_failure(error)

    def test_success_emits_no_exception_event_and_cleans_up(self):
        scenario.run_invoke_agent(self.client)
        self.assertEqual(self.logs.get_finished_logs(), ())
        span = self.spans.get_finished_spans()[-1]
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertIn("Hello", span.attributes["gen_ai.output.messages"])
        self.openai_client.close.assert_called_once_with()
        self.client.agents.delete_version.assert_called_once_with(agent_name="agent", agent_version="1")


if __name__ == "__main__":
    unittest.main()
