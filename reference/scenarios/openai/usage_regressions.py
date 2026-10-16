"""Check counter recording against responses parsed by the OpenAI SDK."""

import os
import unittest
from contextlib import ExitStack
from unittest.mock import DEFAULT, call, patch

import httpx
import openai

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
                _reasoning_output_tokens=DEFAULT,
                _operation_input_tokens=DEFAULT,
                _operation_output_tokens=DEFAULT,
                _reference_tracer=DEFAULT,
            )
        )
        self.stack.enter_context(patch.object(scenario, "reference_event_logger"))

    def run_response(self, usage, *, status="completed", http_status=200):
        body = {
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "model": "gpt-4o-mini",
            "status": status,
            "output": [],
            "usage": usage,
        }
        if status == "failed":
            body["error"] = {"code": "server_error", "message": "Generation failed"}
        transport = httpx.MockTransport(lambda request: httpx.Response(http_status, json=body))
        with openai.OpenAI(
            api_key="mock-key",
            base_url="http://localhost:8080/v1",
            http_client=httpx.Client(transport=transport),
            max_retries=0,
        ) as client:
            scenario.run_responses_compaction_reference(client)

    def run_chat(self, usage, *, audio=False):
        body = {
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-audio-preview" if audio else "gpt-4o-mini",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hi"}}],
            "usage": usage,
        }
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        with openai.OpenAI(
            api_key="mock-key",
            base_url="http://localhost:8080/v1",
            http_client=httpx.Client(transport=transport),
        ) as client:
            if audio:
                scenario.run_chat_audio_reference(client)
            else:
                scenario.run_chat_reference(client)

    def test_absent_usage_does_not_record_any_counter(self):
        for status in ("completed", "failed"):
            with self.subTest(status=status):
                self.run_response(None, status=status)
                for name in (
                    "_input_tokens",
                    "_output_tokens",
                    "_cache_read_input_tokens",
                    "_cache_write_input_tokens",
                    "_reasoning_output_tokens",
                ):
                    self.instruments[name].add.assert_not_called()

    def test_failed_request_without_response_does_not_record_usage(self):
        with self.assertRaises(openai.APIStatusError):
            self.run_response(None, http_status=503)
        for name, instrument in self.instruments.items():
            if name.endswith("_tokens") and not name.startswith("_operation"):
                instrument.add.assert_not_called()

    def test_available_counts_are_recorded_on_success_and_failure(self):
        for status in ("completed", "failed"):
            with self.subTest(status=status):
                self.run_response(
                    {
                        "input_tokens": 12,
                        "output_tokens": 7,
                        "total_tokens": 19,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                    status=status,
                )
                attributes = self.instruments["_input_tokens"].add.call_args.args[1]
                self.assertEqual(attributes["gen_ai.token.modality"], "unknown")
                self.instruments["_input_tokens"].add.assert_called_with(12, attributes)
                self.instruments["_output_tokens"].add.assert_called_with(7, attributes)
                self.instruments["_cache_read_input_tokens"].add.assert_not_called()
                self.instruments["_reasoning_output_tokens"].add.assert_not_called()
                self.instruments["_cache_write_input_tokens"].add.assert_not_called()

    def test_zero_totals_only_record_histograms(self):
        self.run_response({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
        for name in ("_input_tokens", "_output_tokens"):
            self.instruments[name].add.assert_not_called()
        for name in ("_operation_input_tokens", "_operation_output_tokens"):
            self.assertEqual(self.instruments[name].record.call_args.args[0], 0)
            self.instruments[name].record.assert_called_once()
        for name in ("_cache_read_input_tokens", "_cache_write_input_tokens", "_reasoning_output_tokens"):
            self.instruments[name].add.assert_not_called()

    def test_explicit_cache_zero_does_not_record_a_counter_measurement(self):
        self.run_chat(
            {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
                "prompt_tokens_details": {"cached_tokens": 0},
            }
        )
        self.instruments["_cache_read_input_tokens"].add.assert_not_called()
        self.assertEqual(self.instruments["_input_tokens"].add.call_args.args[0], 12)

    def test_positive_cache_and_reasoning_counts_survive_failed_responses(self):
        self.run_response(
            {
                "input_tokens": 12,
                "output_tokens": 7,
                "total_tokens": 19,
                "input_tokens_details": {"cached_tokens": 5},
                "output_tokens_details": {"reasoning_tokens": 2},
            },
            status="failed",
        )
        attributes = self.instruments["_input_tokens"].add.call_args.args[1]
        self.instruments["_cache_read_input_tokens"].add.assert_called_once_with(5, attributes)
        self.instruments["_reasoning_output_tokens"].add.assert_called_once_with(2, attributes)
        self.instruments["_cache_write_input_tokens"].add.assert_not_called()

    def test_audio_contributions_do_not_change_operation_totals(self):
        self.run_chat(
            {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
                "prompt_tokens_details": {"audio_tokens": 5, "cached_tokens": 0},
                "completion_tokens_details": {"audio_tokens": 3, "reasoning_tokens": 0},
            },
            audio=True,
        )
        attributes = self.instruments["_input_tokens"].add.call_args.args[1]
        audio_attributes = {**attributes, "gen_ai.token.modality": "audio"}
        self.assertEqual(
            self.instruments["_input_tokens"].add.call_args_list, [call(5, audio_attributes), call(7, attributes)]
        )
        self.assertEqual(
            self.instruments["_output_tokens"].add.call_args_list, [call(3, audio_attributes), call(4, attributes)]
        )
        histogram_attributes = {key: value for key, value in attributes.items() if key != "gen_ai.token.modality"}
        self.instruments["_operation_input_tokens"].record.assert_called_once_with(12, histogram_attributes)
        self.instruments["_operation_output_tokens"].record.assert_called_once_with(7, histogram_attributes)
        self.instruments["_cache_read_input_tokens"].add.assert_not_called()
        self.instruments["_reasoning_output_tokens"].add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
