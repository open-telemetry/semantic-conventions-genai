"""Loading the committed ``scenarios/<library>/data.json`` files for reports.

The files are written by the conformance runner, which keys every signal by its
registry name (``gen_ai.inference.client``). Reports address span types by the
shorter keys in :mod:`semconv_genai.semconv_model`, so span keys are mapped back
on the way in; events and metrics are already named by the registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
    "realtime_inference",
    "user_speech",
    "embeddings",
    "retrieval",
    "fetch_response",
    "memory",
    "execute_tool",
]

# Display order for event types in reports.
EVENT_TYPE_ORDER = [
    "gen_ai.client.realtime_session.started",
    "gen_ai.client.realtime_session.ended",
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


def _read_instrumented_library(scenario_dir: Path) -> str:
    """Return the library a scenario instruments, from its ``conformance.yaml``.

    Several scenario directories can exercise the same underlying library (the
    Gemini Live scenarios all instrument ``google-genai``; ``openai-realtime``
    instruments ``openai``). Reports group by the declared library so one
    library is listed once, not once per scenario directory.
    """
    conformance = scenario_dir / "conformance.yaml"
    if conformance.is_file():
        for line in conformance.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("instrumented_library:"):
                return stripped.split(":", 1)[1].strip()
    return scenario_dir.name


def _merge_attr_data(
    base: dict[str, dict[str, str]],
    extra: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Combine two scenarios' signal statuses; an attribute is present if either has it."""
    merged = {type_key: dict(attrs) for type_key, attrs in base.items()}
    for type_key, attrs in extra.items():
        target = merged.setdefault(type_key, {})
        for name, status in attrs.items():
            target[name] = "present" if "present" in (target.get(name, "absent"), status) else "absent"
    return merged


def load_scenario_data_files() -> list[ScenarioDataEntry]:
    """Load every committed ``scenarios/<dir>/data.json``, grouped by instrumented library.

    Scenario directories that instrument the same library are merged into a
    single entry keyed by the library declared in ``conformance.yaml``.
    """
    if not SCENARIOS_DIR.is_dir():
        return []
    by_library: dict[str, ScenarioDataEntry] = {}
    for path in sorted(SCENARIOS_DIR.glob("*/data.json")):
        library = _read_instrumented_library(path.parent)
        entry = _normalize_scenario_data_entry(json.loads(path.read_text(encoding="utf-8")), library)
        existing = by_library.get(library)
        if existing is None:
            by_library[library] = entry
        else:
            by_library[library] = ScenarioDataEntry(
                library=library,
                spans=_merge_attr_data(existing.spans, entry.spans),
                events=_merge_attr_data(existing.events, entry.events),
                metrics=_merge_attr_data(existing.metrics, entry.metrics),
            )
    return list(by_library.values())
