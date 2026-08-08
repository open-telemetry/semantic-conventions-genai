"""Verify gen_ai.* metrics survive the committed data files into the reports.

How a run is reduced into ``data.json`` is the conformance runner's business
and is tested there; what is left here is this repo's own view of it -- the
specs the reports are built from and the committed files they read.

Runnable directly (``python tests/test_metrics.py``) or under pytest.
"""

from __future__ import annotations

from semconv_genai.data_files import load_scenario_data_files
from semconv_genai.semconv_model import METRIC_SPECS

_TOOL_CALLS = "gen_ai.invoke_agent.tool_calls"
_INFERENCE_CALLS = "gen_ai.invoke_agent.inference_calls"


def test_metric_specs_expose_recommended_agent_name():
    assert METRIC_SPECS, "expected at least one tracked metric"
    # Only the per-invocation agent metrics are agent-scoped; gen_ai.client.*
    # metrics (token usage, operation duration) are not dimensioned by
    # gen_ai.agent.name, so this checks the invoke_agent metrics specifically
    # rather than every entry in METRIC_SPECS.
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert "gen_ai.agent.name" in METRIC_SPECS[name].recommended, name


def test_metric_specs_are_named_as_the_registry_names_them():
    for name, spec in METRIC_SPECS.items():
        assert spec.registry_id == name, name


def test_committed_google_adk_metrics_round_trip():
    entries = {e.library: e for e in load_scenario_data_files()}
    adk = entries["google-adk"]
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert adk.metrics[name]["gen_ai.agent.name"] == "present", name


if __name__ == "__main__":
    test_metric_specs_expose_recommended_agent_name()
    test_metric_specs_are_named_as_the_registry_names_them()
    test_committed_google_adk_metrics_round_trip()
    print("ok")
