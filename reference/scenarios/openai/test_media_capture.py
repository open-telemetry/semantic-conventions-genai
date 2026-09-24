"""SDK-backed regressions for the audio reference event."""

import base64
import importlib
import json
import os
import unittest
from unittest.mock import patch

import httpx2
import openai
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class AudioCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:8000"}))
        self.scenario = importlib.import_module("scenario")
        self.requests = []
        self.responses = []
        self.reply_text = None
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
        self.client = openai.OpenAI(
            base_url=self.scenario.MOCK_BASE_URL,
            api_key="mock-key",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(self.respond)),
        )
        self.addCleanup(self.client.close)
        self.create = self.client.chat.completions.create
        self.enterContext(patch.object(self.client.chat.completions, "create", side_effect=self.record_response))

    def respond(self, request):
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.host, "127.0.0.1")
        self.assertEqual(request.url.path, "/v1/chat/completions")
        self.requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "chatcmpl-audio",
                "object": "chat.completion",
                "created": 123,
                "model": "model-from-sdk",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": self.reply_text,
                            "audio": {
                                "id": "audio-response",
                                "data": base64.b64encode(b"\xfb\xff").decode("ascii"),
                                "expires_at": 456,
                                "transcript": "Audio transcript from the SDK.",
                            },
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 6,
                    "total_tokens": 15,
                    "prompt_tokens_details": {"audio_tokens": 3, "cached_tokens": 2},
                    "completion_tokens_details": {"audio_tokens": 4, "reasoning_tokens": 1},
                },
            },
        )

    def record_response(self, **kwargs):
        response = self.create(**kwargs)
        self.responses.append(response)
        return response

    def capture(self):
        self.scenario.run_chat_audio_reference(self.client)
        return self.span_exporter.get_finished_spans(), [
            record.log_record for record in self.log_exporter.get_finished_logs()
        ]

    def test_audio_blob_matches_actual_sdk_input(self):
        spans, events = self.capture()
        self.assertEqual((len(self.requests), len(self.responses), len(spans), len(events)), (1, 1, 1, 1))
        request = self.requests[0]
        response = self.responses[0]
        audio_part = request["messages"][0]["content"][1]
        self.assertEqual(audio_part["type"], "input_audio")
        audio = audio_part["input_audio"]
        captured = json.loads(events[0].attributes["gen_ai.input.messages"])
        self.assertEqual(
            captured[0]["parts"][1],
            {"type": "blob", "modality": "audio", "mime_type": f"audio/{audio['format']}", "content": audio["data"]},
        )
        self.assertEqual(
            base64.b64decode(captured[0]["parts"][1]["content"], validate=True),
            base64.b64decode(audio["data"], validate=True),
        )
        self.assertEqual(captured[0]["parts"][0]["content"], request["messages"][0]["content"][0]["text"])
        self.assertEqual(request["modalities"], ["text", "audio"])
        self.assertEqual(events[0].event_name, "gen_ai.client.inference.operation.details")
        self.assertEqual(events[0].span_id, spans[0].context.span_id)
        for attributes in (spans[0].attributes, events[0].attributes):
            self.assertEqual(attributes["gen_ai.operation.name"], "chat")
            self.assertEqual(attributes["gen_ai.request.model"], request["model"])
            self.assertEqual(attributes["gen_ai.response.model"], response.model)
            self.assertEqual(attributes["gen_ai.response.id"], response.id)
            self.assertEqual(list(attributes["gen_ai.response.finish_reasons"]), ["stop"])
            self.assertEqual(
                attributes["gen_ai.usage.audio.input_tokens"], response.usage.prompt_tokens_details.audio_tokens
            )
        self.assertNotIn("gen_ai.input.messages", spans[0].attributes)
        self.assertNotIn("gen_ai.output.messages", spans[0].attributes)
        output = json.loads(events[0].attributes["gen_ai.output.messages"])
        self.assertEqual(
            output[0]["parts"], [{"type": "text", "content": response.choices[0].message.audio.transcript}]
        )

    def test_existing_text_response_is_preserved(self):
        self.reply_text = "Text from the SDK."
        spans, events = self.capture()
        self.assertEqual((len(spans), len(events)), (1, 1))
        output = json.loads(events[0].attributes["gen_ai.output.messages"])
        self.assertEqual(
            output[0]["parts"], [{"type": "text", "content": self.responses[0].choices[0].message.content}]
        )

    def test_disabled_event_sink_does_not_move_content_to_spans(self):
        logger = NoOpLoggerProvider().get_logger("gen_ai.reference")
        with patch.object(self.scenario, "reference_event_logger", return_value=logger):
            spans, events = self.capture()
        self.assertEqual((len(self.requests), len(spans), len(events)), (1, 1, 0))
        self.assertEqual(spans[0].attributes["gen_ai.operation.name"], "chat")
        self.assertNotIn("gen_ai.input.messages", spans[0].attributes)
        self.assertNotIn("gen_ai.output.messages", spans[0].attributes)


if __name__ == "__main__":
    unittest.main()
