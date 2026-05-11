"""Scenario data generation, loading, and attribute coverage computation.

Handles:
  - Computing which attributes are present for each signal type from scenario results
  - Writing per-library data.json files from Weaver results
  - Loading and normalizing committed data.json files for report generation
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from semconv_genai import (
    SCENARIOS_DIR,
    reference_data_file,
    reference_results_dir,
)
from semconv_genai.attribute_spec import AttributeSpec, RequirementLevel
from semconv_genai.classify import classify_span
from semconv_genai.parse_results import (
    ScenarioResult,
    merge_signal_counts,
    parse_result_dir,
)
from semconv_genai.semconv_model import (
    EVENT_SPECS,
    SPAN_SPECS,
)

# ── Attribute coverage computation ──────────────────────────────────

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
    "execute_tool",
]

# Display order for event types in reports.
EVENT_TYPE_ORDER = [
    "gen_ai.client.inference.operation.details",
    "gen_ai.evaluation.result",
]

# Rendering-only: not part of the semconv spec definitions.
DISPLAY_DEPRECATED_ATTRS = {
    "gen_ai.provider.name": "gen_ai.system",
}

_REQUIREMENT_LEVELS = (
    RequirementLevel.REQUIRED,
    RequirementLevel.CONDITIONALLY_REQUIRED,
    RequirementLevel.RECOMMENDED,
    RequirementLevel.OPT_IN,
)


def _present_attributes(result: ScenarioResult) -> set[str]:
    """Return model-backed attribute names present in registry stats."""
    return set(result.observed.attrs)


def _display_attrs_for_level(spec: AttributeSpec, level: RequirementLevel) -> tuple[str, ...]:
    """Return attrs for one requirement level, including deprecated predecessors."""
    display_attrs: list[str] = []
    for attr in sorted(spec.attrs_for_requirement_level(level)):
        display_attrs.append(attr)
        deprecated_attr = DISPLAY_DEPRECATED_ATTRS.get(attr)
        if deprecated_attr is not None:
            display_attrs.append(deprecated_attr)
    return tuple(display_attrs)


def _attrs_by_level(spec: AttributeSpec) -> list[tuple[RequirementLevel, tuple[str, ...]]]:
    """Return non-empty (level, attrs) pairs for a signal-type specification."""
    pairs: list[tuple[RequirementLevel, tuple[str, ...]]] = []
    for level in _REQUIREMENT_LEVELS:
        attrs = _display_attrs_for_level(spec, level)
        if attrs:
            pairs.append((level, attrs))
    return pairs


def attr_names(spec: AttributeSpec) -> list[str]:
    """Return the flat ordered list of display attribute names for a spec."""
    return [attr for _, attrs in _attrs_by_level(spec) for attr in attrs]


def _span_type_present_attributes(
    result: ScenarioResult,
    span_type_key: str,
    level: RequirementLevel,
) -> set[str]:
    """Return attrs present for a span type at the requested requirement level."""
    all_present = _present_attributes(result)
    if level is RequirementLevel.REQUIRED:
        return result.spans.per_type_attrs.get(span_type_key, all_present)
    return result.spans.per_type_any_attrs.get(span_type_key, all_present)


def _relevant_span_type_keys(result: ScenarioResult) -> list[str]:
    """Return span-type keys that are relevant for this result."""
    relevant: list[str] = []
    for span_type_key in SPAN_TYPE_ORDER:
        spec = SPAN_SPECS[span_type_key]
        if not attr_names(spec):
            continue
        if span_type_key in result.spans.detected_types:
            relevant.append(span_type_key)
    return relevant


def _build_statuses_from_present_names(
    expected_names: list[str],
    present_names: list[str] | set[str],
) -> dict[str, str]:
    """Expand a sparse present-name list into present/absent statuses."""
    present = set(present_names)
    return {name: "present" if name in present else "absent" for name in expected_names}


def _build_span_type_present_names(result: ScenarioResult) -> dict[str, list[str]]:
    """Return sparse per-span-type attribute lists for relevant span types."""
    sparse: dict[str, list[str]] = {}
    for span_type_key in _relevant_span_type_keys(result):
        spec = SPAN_SPECS[span_type_key]
        present_names: list[str] = []
        for level, attrs in _attrs_by_level(spec):
            type_present = _span_type_present_attributes(result, span_type_key, level)
            present_names.extend(attr for attr in attrs if attr in type_present)
        sparse[span_type_key] = present_names
    return sparse


def _event_type_present_attributes(
    result: ScenarioResult,
    event_name: str,
    level: RequirementLevel,
) -> set[str]:
    """Return attrs present for an event type at the requested requirement level."""
    all_present = _present_attributes(result)
    if level is RequirementLevel.REQUIRED:
        return result.detected.event_attrs.get(event_name, all_present)
    return result.detected.event_any_attrs.get(event_name, all_present)


def _build_signal_type_present_names(
    attr_specs: dict[str, AttributeSpec],
    merged_counts: dict[str, int],
    present_fn: Callable[[str, RequirementLevel], set[str]],
) -> dict[str, list[str]]:
    """Return sparse per-signal-type attribute lists for detected signals."""
    sparse: dict[str, list[str]] = {}
    for signal_name, spec in attr_specs.items():
        if merged_counts.get(signal_name, 0) <= 0:
            continue
        present_names: list[str] = []
        for level, attrs in _attrs_by_level(spec):
            type_present = present_fn(signal_name, level)
            present_names.extend(attr for attr in attrs if attr in type_present)
        sparse[signal_name] = present_names
    return sparse


def _build_event_type_present_names(result: ScenarioResult) -> dict[str, list[str]]:
    """Return sparse per-event-type attribute lists for detected events."""
    merged = merge_signal_counts(result.observed.events, result.detected.events)
    return _build_signal_type_present_names(
        EVENT_SPECS,
        merged,
        lambda name, level: _event_type_present_attributes(result, name, level),
    )


# ── Scenario data types and generation ──────────────────────────────


@dataclass(frozen=True)
class ScenarioDataEntry:
    library: str
    spans: dict[str, dict[str, str]]
    events: dict[str, dict[str, str]]


def _normalize_generated_scenario_payload(data: dict[str, object]) -> dict[str, object]:
    """Drop empty top-level objects and sort span attribute names alphabetically."""
    normalized: dict[str, object] = {}
    spans = data.get("spans")
    if isinstance(spans, dict) and spans:
        cleaned = {span_type: sorted(attrs) for span_type, attrs in spans.items() if attrs}
        if cleaned:
            normalized["spans"] = cleaned
    events = data.get("events")
    if isinstance(events, dict) and events:
        normalized["events"] = {
            name: sorted(attrs) if isinstance(attrs, (list, set)) else [] for name, attrs in events.items()
        }
    return normalized


def _build_single_scenario_data(result: ScenarioResult) -> tuple[dict[str, object], bool]:
    """Build committed status-report data from a parsed Weaver result."""
    event_present = _build_event_type_present_names(result)
    spans = _build_span_type_present_names(result)

    data: dict[str, object] = {"events": event_present}
    if spans:
        data["spans"] = spans

    return _normalize_generated_scenario_payload(data), bool(spans) or bool(event_present)


def write_generated_scenario_data(library: str) -> Path:
    """Write committed status-report data for one library and return the data.json path."""
    result_dir = reference_results_dir(library)
    result = parse_result_dir(result_dir, library, classify_span)
    if result is None:
        raise ValueError(f"Could not parse Weaver results for library: {library}")

    data, has_relevant_data = _build_single_scenario_data(result)
    if not has_relevant_data:
        raise ValueError(f"No relevant data for library: {library}")

    path = reference_data_file(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


# ── Data file loading and normalization ─────────────────────────────


def _normalize_attr_data(
    value: object,
    attr_specs: dict[str, AttributeSpec],
) -> dict[str, dict[str, str]]:
    """Normalize committed signal data into per-attribute present/absent statuses."""
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for type_key, spec in attr_specs.items():
        if type_key not in value:
            continue

        expected_names = attr_names(spec)
        raw = value[type_key]
        present_names = [name for name in raw if isinstance(name, str)] if isinstance(raw, (dict, list)) else []
        normalized[type_key] = _build_statuses_from_present_names(expected_names, present_names)

    return normalized


def _normalize_scenario_data_entry(entry: dict[str, object], library: str) -> ScenarioDataEntry:
    return ScenarioDataEntry(
        library=library,
        spans=_normalize_attr_data(entry.get("spans"), SPAN_SPECS),
        events=_normalize_attr_data(entry.get("events"), EVENT_SPECS),
    )


def load_scenario_data_files() -> list[ScenarioDataEntry]:
    """Discover and load committed scenario data files from scenarios/.

    Only files in the canonical scenarios/<lib>/data.json layout are considered.
    This avoids pulling in copied workspace artifacts such as node_modules data files.

    Returns normalized typed entries for status-report generation.
    """
    entries: list[ScenarioDataEntry] = []
    if not SCENARIOS_DIR.is_dir():
        return entries
    data_files = sorted(SCENARIOS_DIR.glob("*/data.json"))
    for data_file in data_files:
        data = json.loads(data_file.read_text(encoding="utf-8"))
        library = data_file.parent.name
        entries.append(_normalize_scenario_data_entry(data, library))
    return entries
