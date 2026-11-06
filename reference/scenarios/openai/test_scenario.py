"""Check inference and fetched-stream endings through the OpenAI SDK."""

import json
import os
import unittest
from unittest.mock import patch

import httpx2
import openai
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class StreamingTests(unittest.TestCase):
    def test_inference_endings(self):
        scenario.run_chat_streaming_ttfc_checks()

    def test_cancelled_response(self):
        scenario.run_fetch_response_cancelled_checks()

    def test_fetched_stream_endings(self):
        for status, expected in (
            (None, "interrupted"),
            ("in_progress", "interrupted"),
            ("completed", "stop"),
            ("incomplete", "length"),
            ("failed", "error"),
        ):
            with self.subTest(status=status):
                self.check_fetch(status, expected)

    def test_fetch_stream_error(self):
        self.check_fetch(None, None, stream_error=True)

    def check_fetch(self, status, expected, *, stream_error=False):
        response = {
            "id": "resp-stream",
            "object": "response",
            "created_at": 0,
            "model": "gpt-4o-mini",
            "status": status,
            "output": [],
            "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        }
        payload = {"type": f"response.{status}", "response": response, "sequence_number": 0}
        if stream_error:
            payload = {"error": {"message": "stream failed", "type": "server_error"}}
        body = f"data: {json.dumps(payload)}\n\n" if status or stream_error else ""
        body += "data: [DONE]\n\n"
        responses = []

        def respond(request):
            self.assertEqual(request.url.path, "/v1/responses/resp-stream")
            self.assertEqual(request.url.params["stream"], "true")
            result = httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())
            responses.append(result)
            return result

        exporter = InMemorySpanExporter()
        tp = TracerProvider()
        tp.add_span_processor(SimpleSpanProcessor(exporter))
        self.addCleanup(tp.shutdown)
        with (
            patch.object(scenario, "_reference_tracer", tp.get_tracer("gen_ai.reference")),
            openai.OpenAI(
                base_url="http://127.0.0.1:9999/v1",
                api_key="mock-key",
                max_retries=0,
                http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
            ) as client,
        ):
            if stream_error:
                with self.assertRaises(openai.APIError):
                    scenario._emit_fetch_response_span(client, response["id"], stream=True)
            else:
                scenario._emit_fetch_response_span(client, response["id"], stream=True)
        (span,) = exporter.get_finished_spans()
        self.assertTrue(responses[0].is_closed)
        self.assertTrue(span.attributes["gen_ai.request.stream"])
        self.assertEqual(span.attributes.get("gen_ai.response.status"), status)
        if expected is not None:
            self.assertEqual(span.attributes["gen_ai.response.finish_reasons"], (expected,))
        self.assertEqual(span.status.status_code, StatusCode.ERROR if stream_error else StatusCode.UNSET)
        self.assertEqual("error.type" in span.attributes, stream_error)
        self.assertFalse(any(key.startswith("gen_ai.usage.") for key in span.attributes))


if __name__ == "__main__":
    unittest.main()
