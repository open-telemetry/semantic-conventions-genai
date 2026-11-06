"""Exercise stream endings through the Anthropic SDK without provider calls."""

import json
import os
import unittest
from unittest.mock import patch

import anthropic
import httpx2
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class StreamingTests(unittest.TestCase):
    def check_stream(self, *, close_early=False, stop_reason=None, stream_error=False):
        observed = []
        responses = []
        stream_type = scenario.ObservedStream

        def observe(manager):
            stream = stream_type(manager)
            observed.append(stream)
            return stream

        def events():
            payloads = [
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg-stream",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-4-20250514",
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 10, "output_tokens": 1, "cache_read_input_tokens": 2},
                    },
                },
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": stop_reason}, "usage": {"output_tokens": 3}},
            ]
            if stream_error:
                payloads.append({"type": "error", "error": {"type": "overloaded_error", "message": "stream failed"}})
            else:
                payloads.append({"type": "message_stop"})
            for payload in payloads:
                yield f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n".encode()

        def respond(request):
            self.assertEqual(request.url.path, "/v1/messages")
            self.assertTrue(json.loads(request.content)["stream"])
            response = httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=events())
            responses.append(response)
            return response

        exporter = InMemorySpanExporter()
        tp = TracerProvider()
        tp.add_span_processor(SimpleSpanProcessor(exporter))
        mp = MeterProvider()
        lp = LoggerProvider()
        self.addCleanup(tp.shutdown)
        self.addCleanup(mp.shutdown)
        self.addCleanup(lp.shutdown)
        handler = TelemetryHandler(tracer_provider=tp, meter_provider=mp, logger_provider=lp)
        with (
            patch.object(scenario, "ObservedStream", side_effect=observe),
            patch.object(scenario, "record_inference_usage", wraps=scenario.record_inference_usage) as record_usage,
            anthropic.Anthropic(
                api_key="mock-key",
                base_url="http://127.0.0.1:9999",
                max_retries=0,
                http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
            ) as client,
        ):
            if stream_error:
                with self.assertRaises(anthropic.APIError):
                    scenario.run_chat_streaming_close(handler, client, close_early=close_early)
            else:
                scenario.run_chat_streaming_close(handler, client, close_early=close_early)
        (span,) = exporter.get_finished_spans()
        (stream,) = observed
        self.assertEqual(stream.closed_early, close_early or stream_error)
        self.assertEqual(stream.exhausted, not (close_early or stream_error))
        self.assertTrue(responses[0].is_closed)
        expected_reason = "interrupted" if close_early else stop_reason or ("error" if stream_error else "interrupted")
        self.assertEqual(span.attributes["gen_ai.response.finish_reasons"], (expected_reason,))
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 12)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 1 if close_early else 3)
        record_usage.assert_called_once()
        self.assertEqual(span.status.status_code, StatusCode.ERROR if stream_error else StatusCode.UNSET)
        self.assertEqual("error.type" in span.attributes, stream_error)

    def test_stream_endings(self):
        for options in (
            {},
            {"close_early": True},
            {"stop_reason": "end_turn"},
            {"stream_error": True},
            {"stop_reason": "end_turn", "stream_error": True},
        ):
            with self.subTest(**options):
                self.check_stream(**options)


if __name__ == "__main__":
    unittest.main()
