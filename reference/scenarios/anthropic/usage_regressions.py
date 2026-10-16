"""Check available cache counts at the Anthropic recording boundary."""

import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import DEFAULT, patch

import anthropic
import httpx

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://localhost:8080"}):
    import scenario


class UsageRecordingTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.instruments = self.stack.enter_context(
            patch.multiple(
                scenario,
                _input_tokens=DEFAULT,
                _output_tokens=DEFAULT,
                _cache_read_input_tokens=DEFAULT,
                _cache_write_input_tokens=DEFAULT,
                _operation_input_tokens=DEFAULT,
                _operation_output_tokens=DEFAULT,
            )
        )

    def record(self, usage):
        body = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "Hi"}],
            "stop_reason": "end_turn",
            "usage": usage,
        }
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        with anthropic.Anthropic(
            api_key="mock-key",
            base_url="http://localhost:8080",
            http_client=httpx.Client(transport=transport),
        ) as client:
            response = client.messages.create(
                model="claude-sonnet-4-20250514", max_tokens=10, messages=[{"role": "user", "content": "Hi"}]
            )
        inv = SimpleNamespace(
            input_tokens=None,
            output_tokens=None,
            cache_read_input_tokens=None,
            response_model_name=response.model,
            attributes={},
        )
        if response.usage is not None:
            inv.input_tokens = response.usage.input_tokens
            inv.output_tokens = response.usage.output_tokens
            inv.cache_read_input_tokens = response.usage.cache_read_input_tokens
            cache_write = response.usage.cache_creation_input_tokens
            if cache_write is not None:
                inv.attributes["gen_ai.usage.cache_write.input_tokens"] = cache_write
        scenario.record_inference_usage(inv, response.model, "localhost", 8080)

    def test_explicit_zeros_only_record_histograms(self):
        self.record(
            {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        )
        for name in ("_input_tokens", "_output_tokens", "_cache_read_input_tokens", "_cache_write_input_tokens"):
            self.instruments[name].add.assert_not_called()
        for name in ("_operation_input_tokens", "_operation_output_tokens"):
            self.instruments[name].record.assert_called_once()
            self.assertEqual(self.instruments[name].record.call_args.args[0], 0)

    def test_missing_cache_fields_are_not_inferred_from_totals(self):
        self.record({"input_tokens": 12, "output_tokens": 7})
        self.assertEqual(self.instruments["_input_tokens"].add.call_args.args[0], 12)
        self.assertEqual(self.instruments["_output_tokens"].add.call_args.args[0], 7)
        self.instruments["_cache_read_input_tokens"].add.assert_not_called()
        self.instruments["_cache_write_input_tokens"].add.assert_not_called()

    def test_cache_availability_is_independent(self):
        self.record({"input_tokens": 12, "output_tokens": 7, "cache_creation_input_tokens": 3})
        self.assertEqual(self.instruments["_cache_write_input_tokens"].add.call_args.args[0], 3)
        self.instruments["_cache_read_input_tokens"].add.assert_not_called()

    def test_zero_cache_write_does_not_suppress_positive_cache_read(self):
        self.record(
            {"input_tokens": 12, "output_tokens": 7, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 0}
        )
        attributes = self.instruments["_input_tokens"].add.call_args.args[1]
        self.instruments["_cache_read_input_tokens"].add.assert_called_once_with(3, attributes)
        self.instruments["_cache_write_input_tokens"].add.assert_not_called()

    def test_absent_usage_does_not_record_counters(self):
        self.record(None)
        for name in ("_input_tokens", "_output_tokens", "_cache_read_input_tokens", "_cache_write_input_tokens"):
            self.instruments[name].add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
