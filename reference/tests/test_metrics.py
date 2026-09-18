"""Verify the committed data files survive into the reports.

How a run is reduced into ``data.json`` is the conformance runner's business
and is tested there; what is left here is this repo's own view of it -- the
specs the reports are built from, and the mapping from the registry names a
data file uses onto the shorter keys the reports address signals by.

Runnable directly (``python tests/test_metrics.py``) or under pytest.
"""

from __future__ import annotations

import json
from pathlib import Path

from semconv_genai.data_files import (
    _normalize_scenario_data_entry,
    load_scenario_data_files,
)
from semconv_genai.refinement_coverage import (
    collect_span_refinement_coverage,
    update_span_refinement_coverage,
)
from semconv_genai.report import _render_signal_section
from semconv_genai.semconv_model import metric_specs, span_refinement_specs, span_specs

_TOOL_CALLS = "gen_ai.invoke_agent.tool_calls"
_INFERENCE_CALLS = "gen_ai.invoke_agent.inference_calls"
_TRANSFER_ATTRIBUTES = {
    "gen_ai.transfer.mode",
    "gen_ai.transfer.target.name",
}
_TRANSFER_TARGET_TYPE = "gen_ai.transfer.target.type"
_CALLER_ATTRIBUTES = {
    "gen_ai.caller.type",
    "gen_ai.caller.name",
}


def _attribute_block(model_block: str, attribute: str) -> str:
    return model_block.split(f"- ref: {attribute}", 1)[1].split("\n      - ref:", 1)[0]


def _generated_section(document: str, selector: str) -> str:
    start = document.index(f"<!-- weaver {selector} -->")
    end = document.index("<!-- endweaver -->", start)
    return document[start:end]


def _raw_span(kind: str, attributes: dict[str, object]) -> dict[str, object]:
    return {
        "span": {
            "kind": kind,
            "attributes": [
                {"name": name, "value": value}
                for name, value in attributes.items()
            ],
        }
    }


def test_metric_specs_expose_recommended_agent_name():
    specs = metric_specs()
    assert specs, "expected at least one tracked metric"
    # Only the per-invocation agent metrics are agent-scoped; gen_ai.client.*
    # metrics (token usage, operation duration) are not dimensioned by
    # gen_ai.agent.name, so this checks the invoke_agent metrics specifically
    # rather than every tracked metric.
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert "gen_ai.agent.name" in specs[name].recommended, name


def test_metric_specs_are_named_as_the_registry_names_them():
    for name, spec in metric_specs().items():
        assert spec.registry_id == name, name


def test_execute_tool_duration_does_not_include_transfer_attributes():
    metrics_model = (Path(__file__).parents[2] / "model" / "gen-ai" / "metrics.yaml").read_text(encoding="utf-8")
    execute_tool_duration = metrics_model.split("- name: gen_ai.execute_tool.duration", 1)[1].split(
        "metric_refinements:", 1
    )[0]
    assert "gen_ai.transfer." not in execute_tool_duration


def test_execute_tool_transfer_is_a_span_refinement():
    spans_model = (Path(__file__).parents[2] / "model" / "gen-ai" / "spans.yaml").read_text(encoding="utf-8")
    spans, refinements = spans_model.split("span_refinements:", 1)
    execute_tool = spans.split("- type: gen_ai.execute_tool.internal", 1)[1].split(
        "- type: gen_ai.invoke_workflow.internal", 1
    )[0]

    transfer = refinements.split("- id: gen_ai.execute_tool.transfer.internal", 1)[1]

    assert "applicable refinement" in execute_tool
    assert "SHOULD NOT record two different spans for one call" in execute_tool

    assert "ref: gen_ai.execute_tool.internal" in transfer
    assert "execute_tool {gen_ai.tool.name} {gen_ai.transfer.target.name}" in transfer
    assert "even when the transfer attempt fails" in transfer
    assert "does not produce an additional span" in transfer

    for attribute in (
        "gen_ai.transfer.mode",
        _TRANSFER_TARGET_TYPE,
        "gen_ai.transfer.target.name",
    ):
        assert f"- ref: {attribute}" not in execute_tool
        assert f"- ref: {attribute}" in transfer
        assert "sampling_relevant" not in _attribute_block(transfer, attribute)


def test_transfer_examples_use_target_qualified_names_when_available():
    repository_root = Path(__file__).parents[2]
    scenarios_dir = Path(__file__).parents[1] / "scenarios"

    google_adk = (scenarios_dir / "google-adk" / "scenario.py").read_text(encoding="utf-8")
    openai_agents = (scenarios_dir / "openai-agents" / "scenario.py").read_text(encoding="utf-8")
    langchain = (scenarios_dir / "langchain" / "scenario.py").read_text(encoding="utf-8")
    base_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-spans.md").read_text(encoding="utf-8")
    agent_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-agent-spans.md").read_text(encoding="utf-8")
    interaction_examples = (
        repository_root / "docs" / "gen-ai" / "non-normative" / "examples-agent-interactions.md"
    ).read_text(encoding="utf-8")

    assert 'f"execute_tool {agent_tool.name} {specialist.name}"' in google_adk
    assert 'f"execute_tool {weather_tool.name} {specialist.name}"' in openai_agents
    assert '"execute_tool transfer_to_weather_agent"' in langchain
    assert "gen_ai.transfer.target.type" not in langchain
    assert "[tool-based transfer refinement](gen-ai-agent-spans.md#tool-based-transfer)" in base_spans
    assert "`execute_tool transfer_to_weather_agent weather_agent`" in agent_spans
    assert "`execute_tool transfer_to_weather_agent weather_agent`" in interaction_examples
    assert "`execute_tool transfer_to_weather_agent`" in interaction_examples
    assert "[tool-based transfer refinement](../gen-ai-agent-spans.md#tool-based-transfer)" in interaction_examples


def test_caller_refinement_is_documented_with_workflow_example():
    repository_root = Path(__file__).parents[2]
    agent_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-agent-spans.md").read_text(encoding="utf-8")
    interaction_examples = (
        repository_root / "docs" / "gen-ai" / "non-normative" / "examples-agent-interactions.md"
    ).read_text(encoding="utf-8")

    assert 'select(.id == "gen_ai.invoke_agent.caller.client")' in agent_spans
    assert "### Caller-aware remote invocation" in agent_spans
    assert "[`invoke_agent` caller refinement](#caller-aware-remote-invocation)" in agent_spans
    assert "`gen_ai.caller.type`" in interaction_examples
    assert "`gen_ai.caller.name`" in interaction_examples
    assert "gen_ai.transfer.*` is not recorded because remote invocation" not in interaction_examples
    assert "weather_workflow" in interaction_examples
    assert (
        "[caller-aware refinement](../gen-ai-agent-spans.md#caller-aware-remote-invocation)" in interaction_examples
    )


def test_agent_interaction_refinements_share_a_top_level_section():
    repository_root = Path(__file__).parents[2]
    agent_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-agent-spans.md").read_text(encoding="utf-8")

    interactions = agent_spans.index("## Agent-to-agent interactions")
    caller = agent_spans.index("### Caller-aware remote invocation")
    transfer = agent_spans.index("### Tool-based transfer")

    assert interactions < caller < transfer
    assert "    - [Caller-aware remote invocation](#caller-aware-remote-invocation)" in agent_spans
    assert "    - [Tool-based transfer](#tool-based-transfer)" in agent_spans


def test_generated_base_span_docs_exclude_refinement_only_attributes():
    repository_root = Path(__file__).parents[2]
    agent_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-agent-spans.md").read_text(encoding="utf-8")
    gen_ai_spans = (repository_root / "docs" / "gen-ai" / "gen-ai-spans.md").read_text(encoding="utf-8")

    invoke_agent_base = _generated_section(
        agent_spans,
        '.registry.spans[] | select(.type == "gen_ai.invoke_agent.client")',
    )
    caller_refinement = _generated_section(
        agent_spans,
        '.refinements.spans[] | select(.id == "gen_ai.invoke_agent.caller.client")',
    )
    execute_tool_base = _generated_section(
        gen_ai_spans,
        '.registry.spans[] | select(.type == "gen_ai.execute_tool.internal")',
    )
    transfer_refinement = _generated_section(
        agent_spans,
        '.refinements.spans[] | select(.id == "gen_ai.execute_tool.transfer.internal")',
    )

    assert "gen_ai.caller.type" not in invoke_agent_base
    assert "gen_ai.caller.name" not in invoke_agent_base
    assert "gen_ai.caller.type" in caller_refinement
    assert "gen_ai.caller.name" in caller_refinement

    assert "gen_ai.transfer.mode" not in execute_tool_base
    assert "gen_ai.transfer.target.name" not in execute_tool_base
    assert "gen_ai.transfer.target.type" not in execute_tool_base
    assert "gen_ai.transfer.mode" in transfer_refinement
    assert "gen_ai.transfer.target.name" in transfer_refinement
    assert "gen_ai.transfer.target.type" in transfer_refinement


def test_committed_refinement_reports_preserve_reference_coverage():
    reports = Path(__file__).parents[1] / "reports"
    caller = (reports / "invoke-agent-caller-client-span-refinement.md").read_text(encoding="utf-8")
    transfer = (reports / "execute-tool-transfer-span-refinement.md").read_text(encoding="utf-8")
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")

    assert "| gen_ai.caller.type | [google-adk] |" in caller
    assert "| gen_ai.caller.name | [google-adk] |" in caller
    assert "| gen_ai.transfer.mode | [google-adk], [langchain], [openai-agents] |" in transfer
    assert "| gen_ai.transfer.target.name | [google-adk], [langchain], [openai-agents] |" in transfer
    assert "| gen_ai.transfer.target.type | [google-adk], [openai-agents] |" in transfer
    assert readme.index("[Execute Tool Transfer](reports/execute-tool-transfer-span-refinement.md)") < readme.index(
        "[Invoke Agent Caller](reports/invoke-agent-caller-client-span-refinement.md)"
    )


def test_committed_metrics_do_not_include_transfer_attributes():
    for path in (Path(__file__).parents[1] / "scenarios").glob("*/data.json"):
        metrics = json.loads(path.read_text(encoding="utf-8")).get("metrics", {})
        assert "gen_ai.transfer." not in json.dumps(metrics), path


def test_committed_google_adk_metrics_round_trip():
    entries = {e.library: e for e in load_scenario_data_files()}
    adk = entries["google-adk"]
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert adk.metrics[name]["gen_ai.agent.name"] == "present", name


def test_registry_span_names_map_onto_report_keys():
    """A data file names spans as the registry does; reports use short keys."""
    entry = _normalize_scenario_data_entry(
        {"spans": {"gen_ai.inference.client": ["gen_ai.operation.name"]}},
        "fake",
    )
    assert set(entry.spans) == {"inference"}
    assert entry.spans["inference"]["gen_ai.operation.name"] == "present"
    # Everything else the span type declares is reported as absent, not missing.
    assert entry.spans["inference"]["gen_ai.provider.name"] == "absent"


def test_events_keep_their_registry_names():
    entry = _normalize_scenario_data_entry(
        {"events": {"gen_ai.evaluation.result": ["gen_ai.evaluation.name"]}},
        "fake",
    )
    assert entry.events["gen_ai.evaluation.result"]["gen_ai.evaluation.name"] == "present"


def test_span_types_absent_from_a_data_file_are_not_reported():
    entry = _normalize_scenario_data_entry({"spans": {}}, "fake")
    assert entry.spans == {}


def test_refinement_data_normalizes_against_refinement_specs():
    entry = _normalize_scenario_data_entry(
        {
            "span_refinements": {
                "gen_ai.invoke_agent.caller.client": [
                    "gen_ai.caller.name",
                    "gen_ai.caller.type",
                ]
            }
        },
        "google-adk",
    )

    assert entry.span_refinements["invoke_agent_caller_client"] == {
        "gen_ai.caller.name": "present",
        "gen_ai.caller.type": "present",
    }


def test_generated_refinement_reports_keep_base_and_refinement_coverage_separate(tmp_path):
    entry = _normalize_scenario_data_entry(
        {
            "spans": {
                "gen_ai.invoke_agent.client": [
                    "gen_ai.operation.name",
                    "gen_ai.provider.name",
                ]
            },
            "span_refinements": {
                "gen_ai.invoke_agent.caller.client": [
                    "gen_ai.caller.name",
                    "gen_ai.caller.type",
                ]
            },
        },
        "google-adk",
    )

    page = _render_signal_section(
        [entry],
        "invoke_agent_caller_client",
        span_refinement_specs()["invoke_agent_caller_client"],
        tmp_path,
        "Span Refinement",
        lambda item: item.span_refinements,
    )

    rendered = "\n".join(page)
    assert "# Invoke Agent Caller Span Refinement" in rendered
    assert "| gen_ai.caller.type | [google-adk] |" in rendered
    assert "gen_ai.operation.name" not in rendered


def test_span_specs_are_named_as_the_registry_names_them():
    for key, spec in span_specs().items():
        assert spec.registry_id.startswith("gen_ai."), key


def test_span_refinement_specs_describe_the_same_physical_base_spans():
    caller = span_refinement_specs()["invoke_agent_caller_client"]
    transfer = span_refinement_specs()["execute_tool_transfer"]

    assert caller.registry_id == "gen_ai.invoke_agent.caller.client"
    assert caller.base_registry_id == "gen_ai.invoke_agent.client"
    assert caller.operation_name == "invoke_agent"
    assert caller.span_kind == "client"
    assert caller.discriminator == "gen_ai.caller.type"

    assert transfer.registry_id == "gen_ai.execute_tool.transfer.internal"
    assert transfer.base_registry_id == "gen_ai.execute_tool.internal"
    assert transfer.operation_name == "execute_tool"
    assert transfer.span_kind == "internal"
    assert transfer.discriminator == "gen_ai.transfer.mode"


def test_collect_span_refinement_coverage_uses_discriminators(tmp_path):
    report_dir = tmp_path / "weaver-reports"
    report_dir.mkdir()
    report = {
        "samples": [
            _raw_span(
                "client",
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.caller.type": "workflow",
                    "gen_ai.caller.name": "weather_workflow",
                },
            ),
            _raw_span(
                "internal",
                {
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.transfer.mode": "return_to_caller",
                    "gen_ai.transfer.target.name": "weather_agent",
                    "gen_ai.transfer.target.type": "agent",
                },
            ),
            _raw_span(
                "client",
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": "no_explicit_caller",
                },
            ),
        ]
    }
    (report_dir / "reference.json").write_text(json.dumps(report), encoding="utf-8")

    assert collect_span_refinement_coverage(report_dir) == {
        "gen_ai.execute_tool.transfer.internal": [
            "gen_ai.transfer.mode",
            "gen_ai.transfer.target.name",
            "gen_ai.transfer.target.type",
        ],
        "gen_ai.invoke_agent.caller.client": [
            "gen_ai.caller.name",
            "gen_ai.caller.type",
        ],
    }


def test_update_span_refinement_coverage_preserves_runner_data(tmp_path):
    scenario_dir = tmp_path / "scenario"
    report_dir = scenario_dir / "output" / "weaver-reports"
    report_dir.mkdir(parents=True)
    original = {
        "spans": {"gen_ai.invoke_agent.client": ["gen_ai.operation.name"]},
        "events": {},
        "metrics": {},
        "findings": [],
        "entities": {},
    }
    (scenario_dir / "data.json").write_text(
        json.dumps(original, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "samples": [
            _raw_span(
                "client",
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.caller.type": "workflow",
                    "gen_ai.caller.name": "weather_workflow",
                },
            )
        ]
    }
    (report_dir / "reference.json").write_text(json.dumps(report), encoding="utf-8")

    update_span_refinement_coverage(scenario_dir)

    updated = json.loads((scenario_dir / "data.json").read_text(encoding="utf-8"))
    assert updated["spans"] == original["spans"]
    assert updated["span_refinements"] == {
        "gen_ai.invoke_agent.caller.client": [
            "gen_ai.caller.name",
            "gen_ai.caller.type",
        ]
    }


def test_invoke_agent_client_does_not_duplicate_transfer_target():
    spec = span_specs()["invoke_agent_client"]
    attributes = spec.required + spec.conditionally_required + spec.recommended + spec.opt_in
    assert not any(attribute.startswith("gen_ai.transfer.") for attribute in attributes)


def test_invoke_agent_caller_is_a_span_refinement():
    repository_root = Path(__file__).parents[2]
    registry_model = (repository_root / "model" / "gen-ai" / "registry.yaml").read_text(encoding="utf-8")
    spans_model = (repository_root / "model" / "gen-ai" / "spans.yaml").read_text(encoding="utf-8")
    spans, refinements = spans_model.split("span_refinements:", 1)
    invoke_agent_client = spans.split("- type: gen_ai.invoke_agent.client", 1)[1].split(
        "- type: gen_ai.invoke_agent.internal", 1
    )[0]
    caller = refinements.split("- id: gen_ai.invoke_agent.caller.client", 1)[1].split(
        "\n  - id:", 1
    )[0]

    assert "- key: gen_ai.caller.type" in registry_model
    assert 'value: "agent"' in registry_model
    assert 'value: "workflow"' in registry_model
    assert "- key: gen_ai.caller.name" in registry_model

    assert "ref: gen_ai.invoke_agent.client" in caller
    assert "does not produce an additional span" in caller
    assert "even when the invocation fails" in caller
    assert "MUST NOT infer" in caller
    assert "- ref: gen_ai.transfer." not in caller

    for attribute in _CALLER_ATTRIBUTES:
        assert f"- ref: {attribute}" not in invoke_agent_client
        assert f"- ref: {attribute}" in caller
        assert "sampling_relevant: true" in _attribute_block(caller, attribute)


def test_committed_google_adk_remote_agent_covers_internal_and_client_spans():
    path = Path(__file__).parents[1] / "scenarios" / "google-adk" / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    invoke_agent_internal = data["spans"]["gen_ai.invoke_agent.internal"]
    invoke_agent_client = data["spans"]["gen_ai.invoke_agent.client"]
    caller_refinement = data["span_refinements"]["gen_ai.invoke_agent.caller.client"]
    assert not any(attribute.startswith("gen_ai.transfer.") for attribute in invoke_agent_internal)
    assert "gen_ai.agent.name" in invoke_agent_client
    assert "gen_ai.provider.name" in invoke_agent_client
    assert not any(attribute.startswith("gen_ai.caller.") for attribute in invoke_agent_client)
    assert set(caller_refinement) >= _CALLER_ATTRIBUTES
    assert not any(attribute.startswith("gen_ai.transfer.") for attribute in invoke_agent_client)


def test_google_adk_remote_agent_runs_under_a_named_workflow():
    path = Path(__file__).parents[1] / "scenarios" / "google-adk" / "scenario.py"
    scenario = path.read_text(encoding="utf-8")

    assert "SequentialAgent(" in scenario
    assert 'name="weather_workflow"' in scenario
    assert "sub_agents=[remote_agent]" in scenario
    assert "caller = remote_agent.parent_agent" in scenario
    assert "isinstance(caller, SequentialAgent)" in scenario
    assert "caller.name != workflow.name" in scenario
    assert '"gen_ai.caller.type": "workflow"' in scenario
    assert '"gen_ai.caller.name": caller.name' in scenario
    assert 'attributes.get("gen_ai.caller.type")' in scenario
    assert 'attributes.get("gen_ai.caller.name")' in scenario
    assert 'self.client_caller_type != "workflow"' in scenario
    assert 'self.client_caller_name != "weather_workflow"' in scenario
    assert 'attribute.startswith("gen_ai.caller.")' not in scenario
    assert 'f"invoke_workflow {workflow.name}"' in scenario


def test_committed_transfer_scenarios_emit_transfer_attributes():
    scenarios_dir = Path(__file__).parents[1] / "scenarios"

    expected_attributes = {
        "google-adk": _TRANSFER_ATTRIBUTES | {_TRANSFER_TARGET_TYPE},
        "langchain": _TRANSFER_ATTRIBUTES,
        "openai-agents": _TRANSFER_ATTRIBUTES | {_TRANSFER_TARGET_TYPE},
    }

    for library, expected in expected_attributes.items():
        data = json.loads((scenarios_dir / library / "data.json").read_text(encoding="utf-8"))
        execute_tool = data["spans"].get("gen_ai.execute_tool.internal", [])
        transfer_refinement = data["span_refinements"]["gen_ai.execute_tool.transfer.internal"]

        for attribute in expected:
            assert attribute in transfer_refinement, (library, attribute)
            assert attribute not in execute_tool, (library, attribute)
        assert (_TRANSFER_TARGET_TYPE in transfer_refinement) is (_TRANSFER_TARGET_TYPE in expected), library

        invoke_agent_internal = data["spans"].get("gen_ai.invoke_agent.internal", [])
        assert not any(attribute.startswith("gen_ai.transfer.") for attribute in invoke_agent_internal), library


def test_interaction_type_is_removed_from_committed_scenarios():
    for path in (Path(__file__).parents[1] / "scenarios").glob("*/data.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "gen_ai.agent.interaction.type" not in json.dumps(data), path


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    test_metric_specs_expose_recommended_agent_name()
    test_metric_specs_are_named_as_the_registry_names_them()
    test_execute_tool_duration_does_not_include_transfer_attributes()
    test_execute_tool_transfer_is_a_span_refinement()
    test_transfer_examples_use_target_qualified_names_when_available()
    test_caller_refinement_is_documented_with_workflow_example()
    test_agent_interaction_refinements_share_a_top_level_section()
    test_generated_base_span_docs_exclude_refinement_only_attributes()
    test_committed_refinement_reports_preserve_reference_coverage()
    test_committed_metrics_do_not_include_transfer_attributes()
    test_committed_google_adk_metrics_round_trip()
    test_registry_span_names_map_onto_report_keys()
    test_events_keep_their_registry_names()
    test_span_types_absent_from_a_data_file_are_not_reported()
    test_refinement_data_normalizes_against_refinement_specs()
    with TemporaryDirectory() as tmpdir:
        test_generated_refinement_reports_keep_base_and_refinement_coverage_separate(Path(tmpdir))
    test_span_specs_are_named_as_the_registry_names_them()
    test_span_refinement_specs_describe_the_same_physical_base_spans()
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_collect_span_refinement_coverage_uses_discriminators(tmp_path)
        test_update_span_refinement_coverage_preserves_runner_data(tmp_path)
    test_invoke_agent_client_does_not_duplicate_transfer_target()
    test_invoke_agent_caller_is_a_span_refinement()
    test_committed_google_adk_remote_agent_covers_internal_and_client_spans()
    test_google_adk_remote_agent_runs_under_a_named_workflow()
    test_committed_transfer_scenarios_emit_transfer_attributes()
    test_interaction_type_is_removed_from_committed_scenarios()
    print("ok")
