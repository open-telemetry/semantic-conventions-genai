"""Check native ADK transfers through the real agent and tool runners."""

import os
import unittest
from unittest.mock import patch

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


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
