"""Verify gen_ai.* metrics are captured, persisted, and rendered.

Runnable directly (``python tests/test_metrics.py``) or under pytest.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from semconv_genai.classify import classify_metric
from semconv_genai.data_files import (
    _build_single_scenario_data,
    load_scenario_data_files,
)
from semconv_genai.parse_results import (
    DetectedSignals,
    ObservedTelemetry,
    ScenarioResult,
    SpanClassification,
    _summarize_samples,
)
from semconv_genai.semconv_model import METRIC_SPECS

_TOOL_CALLS = "gen_ai.invoke_agent.tool_calls"
_INFERENCE_CALLS = "gen_ai.invoke_agent.inference_calls"
_TOKEN_USAGE = "gen_ai.client.token.usage"


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
    # Only the per-invocation agent metrics are agent-scoped; gen_ai.client.*
    # metrics (token usage, operation duration) are not dimensioned by
    # gen_ai.agent.name, so this checks the invoke_agent metrics specifically
    # rather than every entry in METRIC_SPECS.
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert "gen_ai.agent.name" in METRIC_SPECS[name].recommended, name


def test_emitted_metric_is_persisted():
    data, has_relevant_data = _build_single_scenario_data(_result_with_tool_calls_metric())
    assert has_relevant_data
    assert data["metrics"][_TOOL_CALLS] == ["gen_ai.agent.name"]


def test_committed_google_adk_metrics_round_trip():
    entries = {e.library: e for e in load_scenario_data_files()}
    adk = entries["google-adk"]
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert adk.metrics[name]["gen_ai.agent.name"] == "present", name


def _samples(metric: dict) -> list[dict]:
    return [{"samples": [{"metric": metric}]}]


def _no_spans(*_args) -> set[str]:
    return set()


def test_metric_attrs_intersect_across_data_points():
    metric = {
        "name": _TOKEN_USAGE,
        "data_points": [
            {"attributes": [{"name": "gen_ai.operation.name"}, {"name": "server.port"}]},
            {"attributes": [{"name": "gen_ai.operation.name"}]},
        ],
    }
    _, signals = _summarize_samples(_samples(metric), _no_spans, classify_metric)
    assert signals.metric_attrs[_TOKEN_USAGE] == {"gen_ai.operation.name"}
    assert signals.metric_any_attrs[_TOKEN_USAGE] == {"gen_ai.operation.name", "server.port"}


def test_untracked_metric_is_ignored():
    metric = {"name": "http.client.request.duration", "data_points": [{"attributes": []}]}
    _, signals = _summarize_samples(_samples(metric), _no_spans, classify_metric)
    assert signals.metrics == {}


class _ListHandler(logging.Handler):
    """Minimal logging handler that stores emitted records in a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _captured_warnings() -> Iterator[list[logging.LogRecord]]:
    """Collect WARNING+ records logged by ``semconv_genai.parse_results``.

    A small stand-in for pytest's ``caplog`` fixture, so tests using it also
    run under ``python tests/test_metrics.py`` and not only under pytest.
    """
    logger = logging.getLogger("semconv_genai.parse_results")
    handler = _ListHandler()
    handler.setLevel(logging.WARNING)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def test_statistics_only_metric_reports_no_supporting_attributes():
    """A metric counted only via statistics has no sample-backed attributes to report.

    The attribute is present elsewhere in the scenario, so the previous fallback
    would have credited it to this metric.
    """
    result = ScenarioResult(
        library="fake",
        statistics=None,
        observed=ObservedTelemetry(metrics={_TOOL_CALLS: 1}, attrs={"gen_ai.agent.name": 1}),
        spans=SpanClassification(),
        detected=DetectedSignals(),
    )
    data, has_relevant_data = _build_single_scenario_data(result)
    assert has_relevant_data
    assert data["metrics"][_TOOL_CALLS] == []


def test_null_data_points_is_skipped_without_warning():
    metric = {"name": _TOKEN_USAGE, "data_points": None}
    with _captured_warnings() as records:
        _, signals = _summarize_samples(_samples(metric), _no_spans, classify_metric)
    assert signals.metrics == {}
    assert records == []


if __name__ == "__main__":
    test_metric_specs_expose_recommended_agent_name()
    test_emitted_metric_is_persisted()
    test_committed_google_adk_metrics_round_trip()
    test_metric_attrs_intersect_across_data_points()
    test_untracked_metric_is_ignored()
    test_statistics_only_metric_reports_no_supporting_attributes()
    test_null_data_points_is_skipped_without_warning()
    print("ok")
