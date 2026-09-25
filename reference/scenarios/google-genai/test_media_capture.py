"""SDK-backed regressions for generated inline media."""

import base64
import importlib
import json
import os
import unittest
from unittest.mock import patch

import httpx
from google import genai
from google.genai import types
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class MediaCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:8000"}))
        self.scenario = importlib.import_module("scenario")
        self.requests = []
        self.responses = []
        self.payloads = [b"\xfb\xff\x00", b"image bytes from the SDK"]
        self.mime_types = ["audio/wav", "image/png"]
        self.include_data = True
        self.include_inline = True
        self.span_exporter = InMemorySpanExporter()
        self.log_exporter = InMemoryLogRecordExporter()
        tracer_provider = TracerProvider(resource=Resource.get_empty())
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        logger_provider = LoggerProvider(resource=Resource.get_empty())
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(self.log_exporter))
        self.addCleanup(tracer_provider.shutdown)
        self.addCleanup(logger_provider.shutdown)
        self.enterContext(
            patch.object(self.scenario, "_reference_tracer", tracer_provider.get_tracer("gen_ai.reference"))
        )
        self.enterContext(
            patch.object(
                self.scenario, "reference_event_logger", return_value=logger_provider.get_logger("gen_ai.reference")
            )
        )
        self.client = genai.Client(
            api_key="mock-key",
            vertexai=False,
            http_options=types.HttpOptions(
                base_url=self.scenario.MOCK_BASE_URL,
                api_version="v1beta",
                httpx_client=httpx.Client(transport=httpx.MockTransport(self.respond)),
            ),
        )
        self.addCleanup(self.client.close)
        self.generate_content = self.client.models.generate_content
        self.enterContext(patch.object(self.client.models, "generate_content", side_effect=self.record_response))
        self.client_factory = self.enterContext(patch.object(genai, "Client", return_value=self.client))

    def respond(self, request):
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.host, "127.0.0.1")
        self.assertEqual(request.url.path, "/v1beta/models/gemini-2.0-flash:generateContent")
        index = len(self.requests)
        self.requests.append(json.loads(request.content))
        parts = [{"text": f"SDK text {index}"}]
        if self.include_inline:
            inline = {"mimeType": self.mime_types[index]}
            if self.include_data:
                inline["data"] = base64.b64encode(self.payloads[index]).decode("ascii")
            parts.append({"inlineData": inline})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP", "index": 0}],
                "modelVersion": "model-from-sdk",
                "responseId": f"media-{index}",
                "usageMetadata": {
                    "promptTokenCount": 9,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 16,
                    "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 9}],
                    "candidatesTokensDetails": [{"modality": "AUDIO", "tokenCount": 7}],
                },
            },
        )

    def record_response(self, **kwargs):
        response = self.generate_content(**kwargs)
        self.responses.append(response)
        return response

    def capture(self):
        self.scenario.run_generate_media()
        return self.span_exporter.get_finished_spans(), [
            record.log_record for record in self.log_exporter.get_finished_logs()
        ]

    def assert_operation(self, spans, events):
        self.assertEqual((len(self.requests), len(self.responses), len(spans), len(events)), (2, 2, 2, 2))
        self.client_factory.assert_called_once()
        self.assertEqual(self.requests[0]["generationConfig"]["responseModalities"], ["TEXT", "IMAGE"])
        self.assertEqual(self.requests[1]["generationConfig"]["responseModalities"], ["AUDIO"])
        for index, (span, event, response) in enumerate(zip(spans, events, self.responses, strict=True)):
            with self.subTest(index=index):
                self.assertEqual(event.event_name, "gen_ai.client.inference.operation.details")
                self.assertEqual(event.span_id, span.context.span_id)
                for attributes in (span.attributes, event.attributes):
                    self.assertEqual(attributes["gen_ai.operation.name"], "chat")
                    self.assertEqual(attributes["gen_ai.provider.name"], "gcp.gemini")
                    self.assertEqual(attributes["gen_ai.request.model"], "gemini-2.0-flash")
                    self.assertEqual(attributes["gen_ai.response.model"], response.model_version)
                    self.assertEqual(
                        attributes["gen_ai.usage.output_tokens"], response.usage_metadata.candidates_token_count
                    )
                    self.assertEqual(
                        list(attributes["gen_ai.response.finish_reasons"]), [str(response.candidates[0].finish_reason)]
                    )
                self.assertNotIn("gen_ai.input.messages", span.attributes)
                self.assertNotIn("gen_ai.output.messages", span.attributes)
                captured_input = json.loads(event.attributes["gen_ai.input.messages"])
                self.assertEqual(
                    captured_input[0]["parts"][0]["content"], self.requests[index]["contents"][0]["parts"][0]["text"]
                )

    def test_media_bytes_and_modality_come_from_sdk_response(self):
        spans, events = self.capture()
        self.assert_operation(spans, events)
        for index, (event, response) in enumerate(zip(events, self.responses, strict=True)):
            with self.subTest(index=index):
                sdk_parts = response.candidates[0].content.parts
                inline = sdk_parts[1].inline_data
                self.assertEqual(inline.data, self.payloads[index])
                output = json.loads(event.attributes["gen_ai.output.messages"])
                self.assertEqual(output[0]["parts"][0], {"type": "text", "content": sdk_parts[0].text})
                self.assertEqual(
                    output[0]["parts"][1],
                    {
                        "type": "blob",
                        "mime_type": inline.mime_type,
                        "modality": inline.mime_type.split("/", 1)[0],
                        "content": base64.b64encode(inline.data).decode("ascii"),
                    },
                )
                self.assertEqual(base64.b64decode(output[0]["parts"][1]["content"], validate=True), inline.data)

    def test_empty_inline_bytes_remain_present(self):
        self.payloads = [b"", b""]
        spans, events = self.capture()
        self.assert_operation(spans, events)
        for event, response in zip(events, self.responses, strict=True):
            self.assertEqual(response.candidates[0].content.parts[1].inline_data.data, b"")
            output = json.loads(event.attributes["gen_ai.output.messages"])
            self.assertEqual(output[0]["parts"][1]["content"], "")

    def test_missing_inline_data_does_not_become_empty_bytes(self):
        self.include_data = False
        spans, events = self.capture()
        self.assert_operation(spans, events)
        for event, response in zip(events, self.responses, strict=True):
            sdk_parts = response.candidates[0].content.parts
            self.assertIsNone(sdk_parts[1].inline_data.data)
            output = json.loads(event.attributes["gen_ai.output.messages"])
            self.assertEqual(output[0]["parts"], [{"type": "text", "content": sdk_parts[0].text}])

    def test_text_only_responses_do_not_invent_media(self):
        self.include_inline = False
        spans, events = self.capture()
        self.assert_operation(spans, events)
        for event, response in zip(events, self.responses, strict=True):
            output = json.loads(event.attributes["gen_ai.output.messages"])
            self.assertEqual(
                output[0]["parts"], [{"type": "text", "content": response.candidates[0].content.parts[0].text}]
            )

    def test_missing_media_type_does_not_invent_modality(self):
        self.mime_types = [None, None]
        spans, events = self.capture()
        self.assert_operation(spans, events)
        for event, response in zip(events, self.responses, strict=True):
            sdk_parts = response.candidates[0].content.parts
            self.assertIsNone(sdk_parts[1].inline_data.mime_type)
            output = json.loads(event.attributes["gen_ai.output.messages"])
            self.assertEqual(output[0]["parts"], [{"type": "text", "content": sdk_parts[0].text}])

    def test_disabled_event_sink_preserves_spans_without_content(self):
        logger = NoOpLoggerProvider().get_logger("gen_ai.reference")
        with patch.object(self.scenario, "reference_event_logger", return_value=logger):
            spans, events = self.capture()
        self.assertEqual((len(self.requests), len(spans), len(events)), (2, 2, 0))
        for span in spans:
            self.assertEqual(span.attributes["gen_ai.operation.name"], "chat")
            self.assertNotIn("gen_ai.input.messages", span.attributes)
            self.assertNotIn("gen_ai.output.messages", span.attributes)


if __name__ == "__main__":
    unittest.main()
