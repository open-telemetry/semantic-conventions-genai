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
        self.client.beta.assistants.create.return_value = SimpleNamespace(
            id="assistant-id", name="assistant", description=None, instructions=None
        )
        self.client.beta.threads.create.return_value = SimpleNamespace(id="thread-id")
        self.run = SimpleNamespace(id="run-id", status="completed", usage=None)
        self.client.beta.threads.runs.create.return_value = self.run
        self.client.beta.threads.runs.submit_tool_outputs.return_value = self.run
        self.client.beta.threads.runs.retrieve.return_value = self.run
        self.client.beta.threads.messages.list.return_value = SimpleNamespace(
            data=[SimpleNamespace(role="assistant", content=[SimpleNamespace(text=SimpleNamespace(value="Hello"))])]
        )

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

    def test_sdk_failures_emit_one_event(self):
        calls = (
            self.client.beta.threads.runs.create,
            self.client.beta.threads.runs.submit_tool_outputs,
            self.client.beta.threads.runs.retrieve,
            self.client.beta.threads.messages.list,
        )
        for call in calls:
            with self.subTest(call=call):
                self.spans.clear()
                self.logs.clear()
                self.run.status = "requires_action"
                error = RuntimeError("SDK call failed")
                call.side_effect = error
                self.assert_invocation_failure(error)
                call.side_effect = None

    def test_tool_argument_processing_failure_emits_one_event(self):
        self.run.status = "requires_action"
        self.run.required_action = SimpleNamespace(
            submit_tool_outputs=SimpleNamespace(
                tool_calls=[SimpleNamespace(id="tool-id", function=SimpleNamespace(name="get_weather", arguments="{}"))]
            )
        )
        with self.assertRaises(KeyError) as raised:
            scenario.run_invoke_agent(self.client)
        span = next(
            span
            for span in self.spans.get_finished_spans()
            if span.attributes["gen_ai.operation.name"] == "invoke_agent"
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], "builtins.KeyError")
        self.assertEqual(span.events, ())
        logs = self.logs.get_finished_logs()
        self.assertEqual(len(logs), 1)
        record = logs[0].log_record
        self.assertEqual(record.event_name, "gen_ai.client.invoke_agent.exception")
        self.assertEqual(record.severity_number, SeverityNumber.WARN)
        self.assertEqual(record.attributes["exception.message"], str(raised.exception))
        self.assertEqual(record.trace_id, span.context.trace_id)
        self.assertEqual(record.span_id, span.context.span_id)
        self.client.beta.threads.runs.submit_tool_outputs.assert_not_called()

    def test_response_processing_failure_emits_one_event(self):
        error = RuntimeError("Cannot read assistant messages")
        messages = Mock()
        type(messages).data = property(Mock(side_effect=error))
        self.client.beta.threads.messages.list.return_value = messages
        self.assert_invocation_failure(error)

    def test_success_emits_no_exception_event_and_deletes_assistant(self):
        scenario.run_invoke_agent(self.client)
        self.assertEqual(self.logs.get_finished_logs(), ())
        span = self.spans.get_finished_spans()[-1]
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertIn("Hello", span.attributes["gen_ai.output.messages"])
        self.client.beta.assistants.delete.assert_called_once_with("assistant-id")


if __name__ == "__main__":
    unittest.main()
