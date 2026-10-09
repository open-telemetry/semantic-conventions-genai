import base64
import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util.genai.handler import TelemetryHandler


class InlineByteSizeTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("anthropic_reference", Path(__file__).with_name("scenario.py"))
        self.scenario = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
            spec.loader.exec_module(self.scenario)

        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        self.addCleanup(self.tracer_provider.shutdown)
        self.log_exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.log_exporter))
        self.addCleanup(self.logger_provider.shutdown)
        self.requests = []

    def _respond(self, request):
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.host, "127.0.0.1")
        self.assertEqual(request.url.path, "/v1/messages")
        self.requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_inline_size",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "Mock response."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
        )

    def _run_scenario(self, name, capture_mode="SPAN_AND_EVENT"):
        self.span_exporter.clear()
        self.log_exporter.clear()
        self.requests.clear()
        client = self.scenario.anthropic.Anthropic(
            base_url=self.scenario.MOCK_BASE_URL,
            api_key="mock-key",
            http_client=httpx2.Client(transport=httpx2.MockTransport(self._respond), trust_env=False),
        )
        self.addCleanup(client.close)
        with (
            patch.dict(
                os.environ,
                {
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": capture_mode,
                    "OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT": "true",
                },
            ),
            patch.object(self.scenario.anthropic, "Anthropic", return_value=client),
        ):
            handler = TelemetryHandler(
                tracer_provider=self.tracer_provider,
                logger_provider=self.logger_provider,
                meter_provider=NoOpMeterProvider(),
            )
            getattr(self.scenario, name)(handler)

        self.assertEqual(len(self.requests), 1, "Measuring inline size must not make another SDK request")
        spans = self.span_exporter.get_finished_spans()
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(spans), 1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].log_record.event_name, "gen_ai.client.inference.operation.details")
        return self.requests[0], spans[0].attributes, logs[0].log_record.attributes

    def _assert_inline_size(self, name, expected_bytes, expected_characters, modality, mime_type):
        request, span_attributes, event_attributes = self._run_scenario(name)
        source = request["messages"][0]["content"][1]["source"]
        payload = base64.b64decode(source["data"], validate=True)
        self.assertEqual(len(payload), expected_bytes)
        self.assertEqual(len(source["data"]), expected_characters)
        span_messages = json.loads(span_attributes["gen_ai.input.messages"])
        event_messages = event_attributes["gen_ai.input.messages"]
        for signal, messages in (("span", span_messages), ("event", event_messages)):
            with self.subTest(signal=signal):
                text, blob = (dict(part) for part in dict(messages[0])["parts"])
                self.assertEqual(blob["type"], "blob")
                self.assertEqual(blob["modality"], modality)
                self.assertEqual(blob["mime_type"], mime_type)
                self.assertIn("byte_size", blob)
                self.assertIs(type(blob["byte_size"]), int)
                self.assertEqual(blob["byte_size"], len(payload))
                self.assertNotEqual(blob["byte_size"], len(source["data"]))
                self.assertNotIn("byte_size", text)
                self.assertEqual(blob["content"], source["data"] if signal == "span" else payload)
        for outputs in (
            json.loads(span_attributes["gen_ai.output.messages"]),
            event_attributes["gen_ai.output.messages"],
        ):
            output = dict(outputs[0])
            self.assertEqual(output["finish_reason"], "end_turn")
            self.assertNotIn("byte_size", dict(output["parts"][0]))

    def test_image_size_counts_decoded_bytes(self):
        self._assert_inline_size("run_chat_with_image_input", 20, 28, "image", "image/png")

    def test_pdf_size_counts_decoded_bytes(self):
        self._assert_inline_size("run_chat_with_document_input", 48, 64, "document", "application/pdf")

    def test_disabled_capture_does_not_emit_content_or_sizes(self):
        for name in ("run_chat_with_image_input", "run_chat_with_document_input"):
            with self.subTest(scenario=name):
                _, span_attributes, event_attributes = self._run_scenario(name, "NO_CONTENT")
                for attributes in (span_attributes, event_attributes):
                    self.assertNotIn("gen_ai.input.messages", attributes)
                    self.assertNotIn("gen_ai.output.messages", attributes)
                    self.assertNotIn("byte_size", attributes)


if __name__ == "__main__":
    unittest.main()
