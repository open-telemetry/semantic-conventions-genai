"""Verify gen_ai.* metrics are captured, persisted, and rendered.

Runnable directly (``python tests/test_metrics.py``) or under pytest.
"""

from __future__ import annotations

from semconv_genai.data_files import (
    _build_single_scenario_data,
    load_scenario_data_files,
)
from semconv_genai.parse_results import (
    DetectedSignals,
    ObservedTelemetry,
    ScenarioResult,
    SpanClassification,
)
from semconv_genai.semconv_model import METRIC_SPECS

_TOOL_CALLS = "gen_ai.invoke_agent.tool_calls"
_INFERENCE_CALLS = "gen_ai.invoke_agent.inference_calls"


def _result_with_tool_calls_metric() -> ScenarioResult:
    return ScenarioResult(
        library="fake",
        statistics=None,
        observed=ObservedTelemetry(metrics={_TOOL_CALLS: 1}),
        spans=SpanClassification(),
        detected=DetectedSignals(
            metrics={_TOOL_CALLS: 1},
            metric_attrs={_TOOL_CALLS: {"gen_ai.agent.name"}},
            metric_any_attrs={_TOOL_CALLS: {"gen_ai.agent.name"}},
        ),
    )


def test_metric_specs_expose_recommended_agent_name():
    assert METRIC_SPECS, "expected at least one tracked metric"
    for name, spec in METRIC_SPECS.items():
        assert "gen_ai.agent.name" in spec.recommended, name


def test_emitted_metric_is_persisted():
    data, has_relevant_data = _build_single_scenario_data(_result_with_tool_calls_metric())
    assert has_relevant_data
    assert data["metrics"][_TOOL_CALLS] == ["gen_ai.agent.name"]


def test_committed_google_adk_metrics_round_trip():
    entries = {e.library: e for e in load_scenario_data_files()}
    adk = entries["google-adk"]
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert adk.metrics[name]["gen_ai.agent.name"] == "present", name


if __name__ == "__main__":
    test_metric_specs_expose_recommended_agent_name()
    test_emitted_metric_is_persisted()
    test_committed_google_adk_metrics_round_trip()
    print("ok")
