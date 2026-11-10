"""Check plugin tool telemetry and mock CLI hook failures."""

import json
import os
import unittest
from unittest.mock import patch

import mock_cli
import scenario
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class HookResponseTests(unittest.TestCase):
    def test_hook_error_response_raises(self):
        response = {
            "type": "control_response",
            "response": {"subtype": "error", "request_id": "cli_req_1", "error": "callback failed"},
        }
        with (
            patch.dict(mock_cli.hook_callback_ids, {"PreToolUse": ["callback_1"]}, clear=True),
            patch.object(mock_cli, "control_request_counter", 0),
            patch.object(mock_cli, "read_message", return_value=response),
            patch.object(mock_cli, "write"),
            self.assertRaisesRegex(RuntimeError, "callback failed"),
        ):
            mock_cli.run_hooks("PreToolUse", {}, "tool_1")

    def test_hook_waits_for_matching_success_response(self):
        responses = [
            {
                "type": "control_response",
                "response": {"subtype": "error", "request_id": "another_request", "error": "unrelated error"},
            },
            {"type": "control_response", "response": {"subtype": "success", "request_id": "cli_req_1"}},
        ]
        with (
            patch.dict(mock_cli.hook_callback_ids, {"PreToolUse": ["callback_1"]}, clear=True),
            patch.object(mock_cli, "control_request_counter", 0),
            patch.object(mock_cli, "read_message", side_effect=responses) as read_message,
            patch.object(mock_cli, "write"),
        ):
            mock_cli.run_hooks("PreToolUse", {}, "tool_1")
        self.assertEqual(read_message.call_count, 2)


class PluginSkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_span_records_hook_arguments_and_result(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        self.addCleanup(provider.shutdown)
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch.object(scenario, "_reference_tracer", provider.get_tracer("test")),
            patch.dict(os.environ),
        ):
            await scenario.run_plugin_skill_reference()

        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        with self.subTest("arguments"):
            self.assertEqual(
                json.loads(attributes.get("gen_ai.tool.call.arguments", "{}")),
                {"skill": "deploy-tools:release-notes"},
            )
        with self.subTest("result"):
            self.assertEqual(
                attributes.get("gen_ai.tool.call.result"),
                "Launching skill: deploy-tools:release-notes",
            )


if __name__ == "__main__":
    unittest.main()
