"""Exercise automatic function calling failures before and after SDK dispatch."""

import os
import unittest
from unittest.mock import patch

from google.genai import _extra_utils, types
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class ToolExceptionTests(unittest.TestCase):
    def setUp(self):
        self.spans = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.addCleanup(provider.shutdown)
        tracer = patch.object(scenario, "_reference_tracer", provider.get_tracer("test"))
        tracer.start()
        self.addCleanup(tracer.stop)

        self.logs = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.logs))
        self.addCleanup(logger_provider.shutdown)
        logger = patch.object(scenario, "reference_event_logger", return_value=logger_provider.get_logger("test"))
        logger.start()
        self.addCleanup(logger.stop)

    def response(self, args):
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[types.Part(function_call=types.FunctionCall(name="get_weather", args=args))]
                    )
                )
            ]
        )

    def assert_failed_tool(self, error):
        spans = self.spans.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["error.type"], f"{type(error).__module__}.{type(error).__qualname__}")
        self.assertEqual(span.events, ())
        logs = self.logs.get_finished_logs()
        self.assertEqual(len(logs), 1)
        record = logs[0].log_record
        self.assertEqual(record.event_name, "gen_ai.execute_tool.exception")
        self.assertEqual(record.severity_number, SeverityNumber.WARN)
        self.assertEqual(record.span_id, span.context.span_id)
        self.assertEqual(record.trace_id, span.context.trace_id)
        self.assertEqual(record.attributes["exception.message"], str(error))

    def test_argument_serialization_failure(self):
        response = self.response({"location": object()})
        original = _extra_utils.get_function_response_parts
        with scenario._patch_automatic_function_calling(), self.assertRaises(TypeError) as caught:
            _extra_utils.get_function_response_parts(response, {"get_weather": lambda location: location})
        self.assertIs(_extra_utils.get_function_response_parts, original)
        self.assert_failed_tool(caught.exception)

    def test_response_copy_failure_is_reraised(self):
        response = self.response({"location": "Seattle"})
        error = RuntimeError("Cannot copy the response")
        with (
            patch.object(types.GenerateContentResponse, "model_copy", side_effect=error),
            scenario._patch_automatic_function_calling(),
            self.assertRaises(RuntimeError) as caught,
        ):
            _extra_utils.get_function_response_parts(response, {"get_weather": lambda location: location})
        self.assertIs(caught.exception, error)
        self.assert_failed_tool(error)

    def test_dispatch_failure_is_reraised(self):
        response = self.response({"location": "Seattle"})
        error = RuntimeError("Dispatch failed")
        with (
            patch.object(_extra_utils, "get_function_response_parts", side_effect=error),
            scenario._patch_automatic_function_calling(),
            self.assertRaises(RuntimeError) as caught,
        ):
            _extra_utils.get_function_response_parts(response, {"get_weather": lambda location: location})
        self.assertIs(caught.exception, error)
        self.assert_failed_tool(error)

    def test_result_serialization_failure(self):
        response = self.response({"location": "Seattle"})

        def get_weather(location: str):
            return {"location": location, "weather": object()}

        with scenario._patch_automatic_function_calling(), self.assertRaises(TypeError) as caught:
            _extra_utils.get_function_response_parts(response, {"get_weather": get_weather})
        self.assert_failed_tool(caught.exception)

    def test_success_preserves_sdk_result_without_exception_log(self):
        response = self.response({"location": "Seattle"})

        def get_weather(location: str):
            return f"Sunny in {location}"

        original = _extra_utils.get_function_response_parts
        expected = original(response, {"get_weather": get_weather})
        with scenario._patch_automatic_function_calling():
            result = _extra_utils.get_function_response_parts(response, {"get_weather": get_weather})
        self.assertEqual(result, expected)
        self.assertIs(_extra_utils.get_function_response_parts, original)
        self.assertEqual(self.logs.get_finished_logs(), ())
        spans = self.spans.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.UNSET)
        self.assertNotIn("error.type", spans[0].attributes)

    def test_sdk_error_to_result_recovery_does_not_emit_exception_log(self):
        response = self.response({"location": "Seattle"})

        def get_weather(location: str):
            raise ValueError(f"No weather for {location}")

        original = _extra_utils.get_function_response_parts
        expected = original(response, {"get_weather": get_weather})
        with scenario._patch_automatic_function_calling():
            result = _extra_utils.get_function_response_parts(response, {"get_weather": get_weather})
        self.assertEqual(result, expected)
        self.assertEqual(self.logs.get_finished_logs(), ())
        spans = self.spans.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.UNSET)
        self.assertNotIn("error.type", spans[0].attributes)


if __name__ == "__main__":
    unittest.main()
