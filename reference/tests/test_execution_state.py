"""Keep runtime state-change coverage and its privacy limits in the reports."""

from semconv_genai.data_files import load_scenario_data_files
from semconv_genai.semconv_model import event_specs

_EVENT = "gen_ai.execution.state.changed"
_COUNT = "gen_ai.execution.state.changed_key.count"
_KEYS = "gen_ai.execution.state.changed_keys"
_VERSION = "gen_ai.execution.state.version"


def test_execution_state_event_requirement_levels():
    spec = event_specs()[_EVENT]
    assert spec.registry_id == _EVENT
    assert spec.required == (_COUNT,)
    assert spec.opt_in == (_KEYS,)
    assert spec.conditionally_required == (_VERSION,)


def test_google_adk_state_coverage_does_not_export_dynamic_keys():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    attributes = entries["google-adk"].events[_EVENT]
    assert attributes[_COUNT] == "present"
    assert attributes[_KEYS] == "absent"
    assert attributes[_VERSION] == "absent"


def test_langgraph_state_coverage_preserves_runtime_version():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    attributes = entries["langgraph"].events[_EVENT]
    for attribute in (_COUNT, _KEYS, _VERSION):
        assert attributes[attribute] == "present"


def test_langgraph_workflow_span_coverage_survives_report_normalization():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    attributes = entries["langgraph"].spans["invoke_workflow"]
    assert attributes["gen_ai.operation.name"] == "present"
    assert attributes["gen_ai.workflow.name"] == "present"
