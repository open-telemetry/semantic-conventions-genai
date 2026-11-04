"""Check native handoff telemetry through the real OpenAI Agents runner."""

import os
import unittest
from unittest.mock import patch

from agents import set_tracing_disabled
from agents.items import ModelResponse
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class NativeHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_handoff_records_sdk_caller_tool_call_and_target(self):
        set_tracing_disabled(True)
        self.addCleanup(set_tracing_disabled, False)
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        self.addCleanup(provider.shutdown)
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        async def respond(model, *args, **kwargs):
            handoffs = kwargs["handoffs"]
            if handoffs:
                output = [
                    ResponseFunctionToolCall(
                        id="handoff-item",
                        call_id="handoff-call",
                        name=handoffs[0].tool_name,
                        arguments="{}",
                        type="function_call",
                    )
                ]
            else:
                output = [
                    ResponseOutputMessage(
                        id="answer",
                        role="assistant",
                        status="completed",
                        type="message",
                        content=[ResponseOutputText(text="Sunny in Seattle.", annotations=[], type="output_text")],
                    )
                ]
            return ModelResponse(
                output=output, usage=Usage(requests=1, input_tokens=12, output_tokens=4), response_id=None
            )

        with (
            patch.object(scenario, "_reference_tracer", provider.get_tracer("test")),
            patch.object(OpenAIChatCompletionsModel, "get_response", respond),
        ):
            await scenario.run_workflow()

        spans = exporter.get_finished_spans()
        transfers = [span for span in spans if span.attributes.get("gen_ai.transfer.mode") == "pass_control"]
        self.assertEqual(len(transfers), 1)
        transfer = transfers[0]
        self.assertEqual(transfer.attributes["gen_ai.agent.name"], "agent-a")
        self.assertEqual(transfer.attributes["gen_ai.transfer.target.name"], "agent-b")
        self.assertEqual(transfer.attributes["gen_ai.tool.call.id"], "handoff-call")
        self.assertEqual(transfer.attributes["gen_ai.tool.call.arguments"], "{}")
        self.assertEqual(transfer.name, f"execute_tool {transfer.attributes['gen_ai.tool.name']}")
        agents = {
            span.attributes["gen_ai.agent.name"]: span
            for span in spans
            if span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        }
        self.assertEqual(set(agents), {"agent-a", "agent-b"})
        self.assertEqual(transfer.parent.span_id, agents["agent-a"].context.span_id)
        self.assertLessEqual(transfer.end_time, agents["agent-b"].start_time)
        self.assertEqual(transfer.context.trace_id, agents["agent-b"].context.trace_id)


if __name__ == "__main__":
    unittest.main()
