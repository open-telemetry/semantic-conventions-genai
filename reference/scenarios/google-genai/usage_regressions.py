"""Check counter recording from Google SDK usage metadata."""

import os
import unittest
from contextlib import ExitStack
from unittest.mock import DEFAULT, call, patch

from google.genai import types

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
                _reasoning_output_tokens=DEFAULT,
                _operation_input_tokens=DEFAULT,
                _operation_output_tokens=DEFAULT,
            )
        )

    def test_absent_fields_do_not_record_counters(self):
        metadata = types.GenerateContentResponseUsageMetadata()
        scenario._record_inference_usage(scenario._usage_attributes(metadata), {})
        for name in ("_input_tokens", "_output_tokens", "_cache_read_input_tokens", "_reasoning_output_tokens"):
            self.instruments[name].add.assert_not_called()

    def test_explicit_zeros_only_record_histograms(self):
        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=0, candidates_token_count=0, cached_content_token_count=0, thoughts_token_count=0
        )
        self.assertEqual(scenario._usage_attributes(usage), {})
        scenario._record_inference_usage(
            {
                "gen_ai.usage.input_tokens": usage.prompt_token_count,
                "gen_ai.usage.output_tokens": usage.candidates_token_count,
                "gen_ai.usage.cache_read.input_tokens": usage.cached_content_token_count,
                "gen_ai.usage.reasoning.output_tokens": usage.thoughts_token_count,
            },
            {},
        )
        for name in ("_input_tokens", "_output_tokens", "_cache_read_input_tokens", "_reasoning_output_tokens"):
            self.instruments[name].add.assert_not_called()
        self.instruments["_operation_input_tokens"].record.assert_called_once_with(0, {})
        self.instruments["_operation_output_tokens"].record.assert_called_once_with(0, {})

    def test_known_totals_without_breakdowns_use_unknown_modality(self):
        usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=12, candidates_token_count=7)
        scenario._record_inference_usage(scenario._usage_attributes(usage), {})
        self.instruments["_input_tokens"].add.assert_called_once_with(12, {"gen_ai.token.modality": "unknown"})
        self.instruments["_output_tokens"].add.assert_called_once_with(7, {"gen_ai.token.modality": "unknown"})
        self.instruments["_cache_read_input_tokens"].add.assert_not_called()
        self.instruments["_reasoning_output_tokens"].add.assert_not_called()

    def test_multimodal_contributions_preserve_totals(self):
        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=30,
            candidates_token_count=7,
            thoughts_token_count=3,
            cached_content_token_count=5,
            prompt_tokens_details=[
                types.ModalityTokenCount(modality="TEXT", token_count=10),
                types.ModalityTokenCount(modality="IMAGE", token_count=20),
            ],
            cache_tokens_details=[types.ModalityTokenCount(modality="TEXT", token_count=5)],
        )
        scenario._record_inference_usage(scenario._usage_attributes(usage), {})
        self.assertEqual(
            self.instruments["_input_tokens"].add.call_args_list,
            [call(10, {"gen_ai.token.modality": "text"}), call(20, {"gen_ai.token.modality": "image"})],
        )
        self.instruments["_output_tokens"].add.assert_called_once_with(10, {"gen_ai.token.modality": "unknown"})
        self.instruments["_cache_read_input_tokens"].add.assert_called_once_with(5, {"gen_ai.token.modality": "text"})
        self.instruments["_reasoning_output_tokens"].add.assert_called_once_with(
            3, {"gen_ai.token.modality": "unknown"}
        )
        self.instruments["_operation_input_tokens"].record.assert_called_once_with(30, {})
        self.instruments["_operation_output_tokens"].record.assert_called_once_with(10, {})

    def test_zero_modalities_are_omitted_but_positive_residuals_are_recorded(self):
        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=30,
            candidates_token_count=7,
            cached_content_token_count=5,
            prompt_tokens_details=[
                types.ModalityTokenCount(modality="TEXT", token_count=0),
                types.ModalityTokenCount(modality="IMAGE", token_count=20),
                types.ModalityTokenCount(modality="AUDIO", token_count=0),
            ],
            candidates_tokens_details=[types.ModalityTokenCount(modality="AUDIO", token_count=0)],
            cache_tokens_details=[
                types.ModalityTokenCount(modality="TEXT", token_count=0),
                types.ModalityTokenCount(modality="IMAGE", token_count=3),
            ],
        )
        scenario._record_inference_usage(scenario._usage_attributes(usage), {})
        self.assertEqual(
            self.instruments["_input_tokens"].add.call_args_list,
            [call(20, {"gen_ai.token.modality": "image"}), call(10, {"gen_ai.token.modality": "unknown"})],
        )
        self.instruments["_output_tokens"].add.assert_called_once_with(7, {"gen_ai.token.modality": "unknown"})
        self.assertEqual(
            self.instruments["_cache_read_input_tokens"].add.call_args_list,
            [call(3, {"gen_ai.token.modality": "image"}), call(2, {"gen_ai.token.modality": "unknown"})],
        )
        self.instruments["_operation_input_tokens"].record.assert_called_once_with(30, {})
        self.instruments["_operation_output_tokens"].record.assert_called_once_with(7, {})


if __name__ == "__main__":
    unittest.main()
