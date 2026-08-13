"""Loading the committed ``scenarios/<library>/data.json`` files for reports.

The files are written by the conformance runner, which keys every signal by its
registry name (``gen_ai.inference.client``). Reports address span types by the
shorter keys in :mod:`semconv_genai.semconv_model`, so span keys are mapped back
on the way in; events and metrics are already named by the registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from semconv_genai import SCENARIOS_DIR
from semconv_genai.attribute_spec import AttributeSpec, RequirementLevel
from semconv_genai.semconv_model import (
    event_specs,
    metric_specs,
    span_specs,
)

# Display order for span types in reports.
SPAN_TYPE_ORDER = [
    "create_agent",
    "invoke_agent_client",
    "invoke_agent_internal",
    "invoke_workflow",
    "plan",
    "inference",
    "embeddings",
    "retrieval",
    "fetch_response",
    "memory",
    "execute_tool",
]

# Display order for event types in reports.
EVENT_TYPE_ORDER = [
    "gen_ai.client.inference.operation.details",
    "gen_ai.evaluation.result",
]


def metric_type_order() -> tuple[str, ...]:
    """Display order for metric types in reports."""
    return tuple(metric_specs())


_REQUIREMENT_LEVELS = (
    RequirementLevel.REQUIRED,
    RequirementLevel.CONDITIONALLY_REQUIRED,
    RequirementLevel.RECOMMENDED,
    RequirementLevel.OPT_IN,
)


def _attrs_by_level(spec: AttributeSpec) -> list[tuple[RequirementLevel, tuple[str, ...]]]:
    """Return non-empty (level, attrs) pairs for a signal-type specification."""
    pairs: list[tuple[RequirementLevel, tuple[str, ...]]] = []
    for level in _REQUIREMENT_LEVELS:
        attrs = tuple(sorted(spec.attrs_for_requirement_level(level)))
        if attrs:
            pairs.append((level, attrs))
    return pairs


def attr_names(spec: AttributeSpec) -> list[str]:
    """Return the flat ordered list of display attribute names for a spec."""
    return [attr for _, attrs in _attrs_by_level(spec) for attr in attrs]


@dataclass(frozen=True)
class ScenarioDataEntry:
    library: str
    spans: dict[str, dict[str, str]]
    events: dict[str, dict[str, str]]
    metrics: dict[str, dict[str, str]]


def _normalize_attr_data(
    value: object,
    attr_specs: dict[str, AttributeSpec],
) -> dict[str, dict[str, str]]:
    """Expand the recorded attribute names into present/absent statuses."""
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for type_key, spec in attr_specs.items():
        if spec.registry_id not in value:
            continue
        recorded = value[spec.registry_id]
        present = set(recorded) if isinstance(recorded, (dict, list)) else set()
        normalized[type_key] = {name: "present" if name in present else "absent" for name in attr_names(spec)}
    return normalized


def _normalize_scenario_data_entry(entry: dict[str, object], library: str) -> ScenarioDataEntry:
    return ScenarioDataEntry(
        library=library,
        spans=_normalize_attr_data(entry.get("spans"), span_specs()),
        events=_normalize_attr_data(entry.get("events"), event_specs()),
        metrics=_normalize_attr_data(entry.get("metrics"), metric_specs()),
    )


def load_scenario_data_files() -> list[ScenarioDataEntry]:
    """Load every committed ``scenarios/<library>/data.json``."""
    if not SCENARIOS_DIR.is_dir():
        return []
    return [
        _normalize_scenario_data_entry(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
        for path in sorted(SCENARIOS_DIR.glob("*/data.json"))
    ]
