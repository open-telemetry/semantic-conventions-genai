"""Check usage accounting through real Groq SDK success and failure paths."""

import json
import os
import unittest
from unittest.mock import patch

import groq
import httpx
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

os.environ.setdefault("MOCK_LLM_URL", "http://localhost/v1")

import scenario


class UsageTests(unittest.TestCase):
    def check_call(self, call, mode):
        base = {"id": "test-completion", "object": "chat.completion", "created": 0, "model": "llama-3.1-8b-instant"}
        usage = (
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if mode == "zero"
            else {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
        )

        class BrokenStream(httpx.SyncByteStream):
            def __iter__(self):
                chunk = {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n".encode()
                raise httpx.ReadError("stream interrupted")

        def respond(request):
            if mode == "error":
                return httpx.Response(500, json={"error": {"message": "failure", "type": "server_error"}})
            if mode == "stream_error":
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BrokenStream())
            if json.loads(request.content).get("stream"):
                chunk = {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": "stop"}],
                }
                if mode in {"usage", "zero"}:
                    chunk["x_groq"] = {"usage": usage}
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode(),
                )
            return httpx.Response(
                200,
                json={
                    **base,
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
                    ],
                    "usage": usage if mode in {"usage", "zero"} else None,
                },
            )

        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])
        tracer_provider = TracerProvider()
        exporter = InMemorySpanExporter()
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        meter = meter_provider.get_meter("groq.usage.checks")
        instruments = {
            "_input_tokens": meter.create_histogram(
                "input", explicit_bucket_boundaries_advisory=scenario._TOKEN_BUCKETS
            ),
            "_output_tokens": meter.create_histogram(
                "output", explicit_bucket_boundaries_advisory=scenario._TOKEN_BUCKETS
            ),
            "_inference_duration": meter.create_histogram("duration"),
            "_input_token_usage": meter.create_counter("input_usage"),
            "_output_token_usage": meter.create_counter("output_usage"),
        }
        try:
            with (
                patch.multiple(scenario, **instruments, _reference_tracer=tracer_provider.get_tracer("groq.checks")),
                groq.Groq(
                    base_url="http://localhost/v1",
                    api_key="mock-key",
                    max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(respond)),
                ) as client,
            ):
                if mode in {"error", "stream_error"}:
                    with self.assertRaises((groq.APIStatusError, httpx.ReadError)):
                        call(client)
                else:
                    call(client)
            metrics = {
                metric.name: metric.data.data_points
                for resource in reader.get_metrics_data().resource_metrics
                for scope in resource.scope_metrics
                for metric in scope.metrics
            }
            for name, total in (("input", 5), ("output", 2)):
                points = metrics[name]
                self.assertEqual(len(points), 1)
                self.assertEqual(points[0].count, 1)
                self.assertEqual(points[0].sum, total if mode == "usage" else 0)
                self.assertEqual(list(points[0].explicit_bounds), scenario._TOKEN_BUCKETS)
                self.assertNotIn("gen_ai.token.modality", points[0].attributes)
                if mode == "usage":
                    self.assertEqual(metrics[f"{name}_usage"][0].value, total)
                    self.assertEqual(metrics[f"{name}_usage"][0].attributes["gen_ai.token.modality"], "unknown")
                else:
                    self.assertNotIn(f"{name}_usage", metrics)
            self.assertEqual(metrics["duration"][0].count, 1)
            spans = exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            if mode in {"error", "stream_error"}:
                self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
                self.assertEqual(metrics["input"][0].attributes["error.type"], spans[0].attributes["error.type"])
                self.assertEqual(metrics["output"][0].attributes["error.type"], spans[0].attributes["error.type"])
            else:
                self.assertNotIn("error.type", spans[0].attributes)
        finally:
            meter_provider.shutdown()
            tracer_provider.shutdown()

    def test_calls(self):
        for call in (
            scenario.run_chat_reference,
            scenario.run_chat_streaming_reference,
            scenario.run_chat_tool_call_reference,
        ):
            for mode in ("usage", "zero", "missing", "error"):
                with self.subTest(call=call.__name__, mode=mode):
                    self.check_call(call, mode)

    def test_stream_failure(self):
        self.check_call(scenario.run_chat_streaming_reference, "stream_error")


if __name__ == "__main__":
    unittest.main()
