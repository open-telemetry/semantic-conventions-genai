"""Exercise chunk timing through the real OpenAI SDK, without a model service."""

import json
import os
import unittest
from unittest.mock import patch

import httpx2
from openai import APIConnectionError, OpenAI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

os.environ.setdefault("MOCK_LLM_URL", "http://localhost:8080")

import scenario


def event(*deltas, usage=None, finish_reason=None):
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [
            {"index": index, "delta": delta, "finish_reason": finish_reason} for index, delta in enumerate(deltas)
        ],
        "usage": usage,
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


class StreamingTimingTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(metric_readers=[self.reader])
        meter = self.meter_provider.get_meter("gen_ai.reference")
        self.exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.addCleanup(self.meter_provider.shutdown)
        self.addCleanup(self.tracer_provider.shutdown)
        self.enterContext(patch.object(scenario, "monotonic", lambda: self.now))
        self.enterContext(patch.object(scenario, "_reference_tracer", self.tracer_provider.get_tracer("test")))
        self.enterContext(
            patch.object(
                scenario,
                "_time_to_first_chunk",
                meter.create_histogram("gen_ai.client.inference.time_to_first_chunk", unit="s"),
            )
        )
        self.enterContext(
            patch.object(
                scenario,
                "_time_per_output_chunk",
                meter.create_histogram("gen_ai.client.inference.time_per_output_chunk", unit="s"),
            )
        )

    def advance(self, seconds):
        self.now += seconds

    def run_stream(self, entries, *, retries=0):
        # The SDK still performs request construction, retries, SSE decoding,
        # and response-model parsing. Only the HTTP transport and clock are fake.
        advance = self.advance

        class Stream(httpx2.SyncByteStream):
            def __iter__(self):
                for delay, data in entries:
                    advance(delay)
                    if isinstance(data, Exception):
                        raise data
                    yield data
                yield b"data: [DONE]\n\n"

        attempts = []

        def handle(request):
            attempts.append(request)
            if len(attempts) <= retries:
                advance(0.25)
                return httpx2.Response(429, headers={"retry-after-ms": "1000"}, json={"error": "retry"})
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

        with (
            patch("openai._base_client.time.sleep", side_effect=self.advance),
            httpx2.Client(transport=httpx2.MockTransport(handle)) as http_client,
            OpenAI(
                api_key="test",
                base_url="http://localhost:8080/v1",
                http_client=http_client,
                max_retries=retries,
            ) as client,
        ):
            scenario.run_chat_streaming_reference(client)
        self.assertEqual(len(attempts), retries + 1)

    def measurements(self):
        data = self.reader.get_metrics_data()
        if data is None:
            return {}
        return {
            metric.name.rsplit(".", 1)[-1]: metric.data.data_points[0]
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }

    def assert_timing(self, first, intervals):
        measurements = self.measurements()
        span = self.exporter.get_finished_spans()[0]
        if first is None:
            self.assertNotIn("time_to_first_chunk", measurements)
            self.assertNotIn("gen_ai.response.time_to_first_chunk", span.attributes)
        else:
            self.assertEqual(measurements["time_to_first_chunk"].count, 1)
            self.assertAlmostEqual(measurements["time_to_first_chunk"].sum, first)
            self.assertAlmostEqual(span.attributes["gen_ai.response.time_to_first_chunk"], first)
        if not intervals:
            self.assertNotIn("time_per_output_chunk", measurements)
        else:
            point = measurements["time_per_output_chunk"]
            self.assertEqual(point.count, len(intervals))
            self.assertAlmostEqual(point.sum, sum(intervals))
            self.assertAlmostEqual(point.min, min(intervals))
            self.assertAlmostEqual(point.max, max(intervals))

    def test_retries_and_ignored_events_do_not_restart_timing(self):
        usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
        self.run_stream(
            [
                (0.1, event({"role": "assistant", "content": ""})),
                (0.2, event({"content": "Hello"})),
                (0.3, event(usage=usage)),
                (0.4, event({"content": " world"})),
                (0.1, event({}, finish_reason="stop")),
            ],
            retries=2,
        )
        # Two failed 0.25s attempts and two 1s backoffs precede the stream.
        self.assert_timing(2.8, [0.7])

    def test_empty_stream_has_no_timing(self):
        self.run_stream([(0.1, event({"role": "assistant"})), (0.2, event({}, finish_reason="stop"))])
        self.assert_timing(None, [])

    def test_single_chunk_has_only_first_chunk_timing(self):
        self.run_stream([(0.1, event({"refusal": "I cannot help with that."}))])
        self.assert_timing(0.1, [])

    def test_multiple_choices_count_once(self):
        self.run_stream([(0.1, event({"content": "one"}, {"content": "two"})), (0.2, event({"content": "three"}))])
        self.assert_timing(0.1, [0.2])

    def test_audio_metadata_does_not_count_as_output(self):
        self.run_stream(
            [
                (0.1, event({"audio": {"id": "audio-test"}})),
                (0.2, event({"audio": {"data": "AA=="}})),
                (0.3, event({"audio": {"expires_at": 1234567890}})),
                (0.4, event({"audio": {"transcript": "hello"}})),
            ]
        )
        self.assert_timing(0.3, [0.7])

    def test_tool_name_and_arguments_count_but_id_does_not(self):
        self.run_stream(
            [
                (0.1, event({"tool_calls": [{"index": 0, "id": "call-test", "type": "function"}]})),
                (0.2, event({"tool_calls": [{"index": 0, "function": {"name": "get_weather"}}]})),
                (0.3, event({"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]})),
            ]
        )
        self.assert_timing(0.3, [0.3])

    def test_transport_fragments_do_not_define_chunks(self):
        first = event({"content": "first"})
        self.run_stream(
            [
                (0.1, first[:20]),
                (0.2, first[20:]),
                (0.3, event({"content": "second"}) + event({"content": "third"})),
            ]
        )
        self.assert_timing(0.3, [0.3, 0.0])

    def test_output_with_usage_counts_once(self):
        self.run_stream(
            [(0.1, event({"content": "hello"}, usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}))]
        )
        self.assert_timing(0.1, [])

    def test_interrupted_stream_retains_measurements(self):
        with self.assertRaises(APIConnectionError):
            self.run_stream(
                [
                    (0.1, event({"content": "first"})),
                    (0.2, event({"content": "second"})),
                    (0.3, httpx2.ReadError("lost")),
                ]
            )
        self.assert_timing(0.1, [0.2])

    def test_failure_before_output_has_no_timing(self):
        with self.assertRaises(APIConnectionError):
            self.run_stream([(0.1, event({"role": "assistant"})), (0.2, httpx2.ReadError("lost"))])
        self.assert_timing(None, [])


if __name__ == "__main__":
    unittest.main()
