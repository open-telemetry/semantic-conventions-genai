"""Regression tests for `_usage_attributes` in the Google GenAI reference scenario.

An explicit zero in the SDK usage metadata is a real observation and must reach
`gen_ai.usage.output_tokens`; only usage that the SDK did not report (None) may
leave the attribute unset. Run from this directory with the scenario's own
environment:

    MOCK_LLM_URL=http://unused uv run --with pytest pytest -q test_usage_attributes.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_OUTPUT = "gen_ai.usage.output_tokens"
_REASONING = "gen_ai.usage.reasoning.output_tokens"


@pytest.fixture(scope="module")
def scenario():
    os.environ.setdefault("MOCK_LLM_URL", "http://unused")
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("google_genai_scenario", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _usage(candidates, thoughts):
    return SimpleNamespace(
        prompt_token_count=5,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )


@pytest.mark.parametrize(
    ("candidates", "thoughts", "expected"),
    [
        (0, 0, 0),
        (0, None, 0),
        (None, 0, 0),
        (10, None, 10),
        (10, 5, 15),
    ],
)
def test_explicit_zero_and_positive_output_tokens_are_reported(scenario, candidates, thoughts, expected):
    attrs = scenario._usage_attributes(_usage(candidates, thoughts))
    assert attrs[_OUTPUT] == expected


def test_unreported_output_tokens_leave_the_attribute_unset(scenario):
    attrs = scenario._usage_attributes(_usage(None, None))
    assert _OUTPUT not in attrs


def test_reasoning_tokens_are_added_once(scenario):
    attrs = scenario._usage_attributes(_usage(10, 5))
    assert attrs[_OUTPUT] == 15
    assert attrs[_REASONING] == 5
