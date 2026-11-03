"""Check ADK retries and native transfers through the real agent and tool runners."""

import os
import unittest
from unittest.mock import patch

import httpx
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class InferenceRetryTests(unittest.TestCase):
    def test_sdk_retry_counts_one_inference_call(self):
        attempts = 0
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        histogram = provider.get_meter("test").create_histogram(
            "gen_ai.invoke_agent.inference_calls", unit="{inference_call}"
        )
        self.addCleanup(provider.shutdown)

        def respond(request):
            nonlocal attempts
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/models/gemini-2.0-flash:generateContent"))
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": {"code": 503, "message": "Unavailable"}})
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"role": "model", "parts": [{"text": "Hello."}]}, "finishReason": "STOP"}
                    ],
                    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4, "totalTokenCount": 16},
                },
            )

        class RetryingGemini(Gemini):
            def __init__(self, **kwargs):
                super().__init__(
                    **kwargs,
                    client_kwargs={
                        "api_key": "mock-key",
                        "vertexai": False,
                        "http_options": types.HttpOptions(
                            base_url=kwargs["base_url"],
                            retry_options=types.HttpRetryOptions(attempts=2, initial_delay=0.001, jitter=0.001),
                            async_client_args={"transport": httpx.MockTransport(respond)},
                        ),
                    },
                )

        with (
            patch("google.adk.models.google_llm.Gemini", RetryingGemini),
            patch.object(scenario, "_inference_calls", histogram),
        ):
            scenario.run_agent_reference()

        self.assertEqual(attempts, 2)
        metrics = [
            metric
            for resource in reader.get_metrics_data().resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == "gen_ai.invoke_agent.inference_calls"
        ]
        self.assertEqual(len(metrics), 1)
        points = metrics[0].data.data_points
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].attributes, {"gen_ai.agent.name": "test_agent"})
        self.assertEqual(points[0].count, 1)
        self.assertEqual(points[0].sum, 1)


class NativeTransferTests(unittest.TestCase):
    def test_transfer_records_caller_target_and_separate_agent_execution(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        async def respond(model, llm_request, stream=False):
            if "transfer_to_agent" in llm_request.tools_dict:
                part = types.Part(
                    function_call=types.FunctionCall(
                        id="transfer-call",
                        name="transfer_to_agent",
                        args={"agent_name": "weather_specialist"},
                    )
                )
            else:
                part = types.Part(text="Sunny in Seattle.")
            yield LlmResponse(
                content=types.Content(role="model", parts=[part]),
                finish_reason=types.FinishReason.STOP,
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=12, candidates_token_count=4
                ),
            )

        with (
            patch.object(scenario, "_reference_tracer", provider.get_tracer("test")),
            patch.object(Gemini, "generate_content_async", respond),
        ):
            self.assertTrue(
                callable(getattr(scenario, "run_multi_agent_handoff_reference", None)),
                "The scenario must exercise ADK's native transfer_to_agent tool",
            )
            scenario.run_multi_agent_handoff_reference()

        spans = exporter.get_finished_spans()
        transfers = [span for span in spans if span.attributes.get("gen_ai.transfer.mode") == "pass_control"]
        self.assertEqual(len(transfers), 1)
        transfer = transfers[0]
        self.assertEqual(transfer.name, "execute_tool transfer_to_agent")
        self.assertEqual(transfer.attributes["gen_ai.agent.name"], "root_agent")
        self.assertEqual(transfer.attributes["gen_ai.transfer.target.name"], "weather_specialist")
        self.assertEqual(transfer.attributes["gen_ai.tool.call.id"], "transfer-call")
        agents = {
            span.attributes["gen_ai.agent.name"]: span
            for span in spans
            if span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        }
        self.assertEqual(set(agents), {"root_agent", "weather_specialist"})
        self.assertEqual(transfer.parent.span_id, agents["root_agent"].context.span_id)
        self.assertLessEqual(transfer.end_time, agents["weather_specialist"].start_time)
        self.assertEqual(transfer.context.trace_id, agents["weather_specialist"].context.trace_id)
        for agent in agents.values():
            self.assertEqual(agent.attributes["gen_ai.usage.input_tokens"], 12)
            self.assertEqual(agent.attributes["gen_ai.usage.output_tokens"], 4)
        provider.shutdown()


if __name__ == "__main__":
    unittest.main()
