"""Check available cache counts at the Anthropic recording boundary."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import DEFAULT, patch

from anthropic.types import Usage

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://localhost:8080"}):
    import scenario


class UsageRecordingTest(unittest.TestCase):
    def setUp(self):
        self.instruments = self.enterContext(
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
        usage = Usage.model_validate(usage) if usage is not None else None
        inv = SimpleNamespace(
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cache_read_input_tokens=usage.cache_read_input_tokens if usage else None,
            response_model_name=None,
            attributes={"gen_ai.usage.cache_write.input_tokens": usage.cache_creation_input_tokens} if usage else {},
        )
        scenario.record_inference_usage(inv, "claude-sonnet-4-20250514", "localhost", 8080)

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
