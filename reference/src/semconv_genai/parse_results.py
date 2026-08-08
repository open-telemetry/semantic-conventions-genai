"""Parse and classify Weaver live-check output into ScenarioResult objects."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# ── Span classification types ──────────────────────────────────────


@dataclass
class SpanClassification:
    detected_types: set[str] = field(default_factory=set)
    per_type_attrs: dict[str, set[str]] = field(default_factory=dict)
    per_type_any_attrs: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class DetectedSignals:
    events: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, int] = field(default_factory=dict)
    event_attrs: dict[str, set[str]] = field(default_factory=dict)
    event_any_attrs: dict[str, set[str]] = field(default_factory=dict)
    metric_attrs: dict[str, set[str]] = field(default_factory=dict)
    metric_any_attrs: dict[str, set[str]] = field(default_factory=dict)


ClassifySpan = Callable[[str, str, dict[str, object]], set[str]]
ClassifyMetric = Callable[[str, dict[str, object]], set[str]]


def _attributes_by_name(
    owner: dict[str, object],
    include_attr: Callable[[dict[str, object]], bool] | None = None,
) -> dict[str, object]:
    attrs: dict[str, object] = {}
    raw_attrs = owner.get("attributes", [])
    if not isinstance(raw_attrs, list):
        return attrs
    for attr in raw_attrs:
        if not isinstance(attr, dict):
            continue
        name = attr.get("name")
        if not isinstance(name, str) or not name:
            continue
        if include_attr is not None and not include_attr(attr):
            continue
        attrs[name] = attr.get("value")
    return attrs


def _attribute_names(
    owner: dict[str, object],
    include_attr: Callable[[dict[str, object]], bool] | None = None,
) -> set[str]:
    names: set[str] = set()
    raw_attrs = owner.get("attributes", [])
    if not isinstance(raw_attrs, list):
        return names
    for attr in raw_attrs:
        if not isinstance(attr, dict):
            continue
        name = attr.get("name")
        if not isinstance(name, str) or not name:
            continue
        if include_attr is not None and not include_attr(attr):
            continue
        names.add(name)
    return names


def _metric_data_points(metric: dict[str, object]) -> list[dict[str, object]] | None:
    """Return the metric's data points, or None if `data_points` is unusable."""
    raw_points = metric.get("data_points")
    if raw_points is None:
        return []
    if not isinstance(raw_points, list):
        _LOGGER.warning(
            "Skipping metric %r with invalid data_points: expected list, got %s",
            metric.get("name", ""),
            type(raw_points).__name__,
        )
        return None

    data_points: list[dict[str, object]] = []
    for data_point in raw_points:
        if isinstance(data_point, dict):
            data_points.append(data_point)
            continue
        _LOGGER.warning(
            "Skipping non-dict data point for metric %r: %r",
            metric.get("name", ""),
            data_point,
        )
    return data_points


def _summarize_samples(
    all_objects: list[dict],
    classify_span: ClassifySpan,
    classify_metric: ClassifyMetric,
    include_attr: Callable[[dict[str, object]], bool] | None = None,
) -> tuple[SpanClassification, DetectedSignals]:
    """Scan sample payloads once and collect detected spans, events, and metrics."""
    spans = SpanClassification()
    signals = DetectedSignals()
    for obj in all_objects:
        if not isinstance(obj, dict):
            continue
        for sample in obj.get("samples", []):
            span = sample.get("span")
            if span:
                attrs = _attributes_by_name(span, include_attr)
                classified = classify_span(
                    str(span.get("name", "")),
                    str(span.get("kind", "")),
                    attrs,
                )
                spans.detected_types.update(classified)
                attr_names = _attribute_names(span, include_attr)
                for span_type in classified:
                    if span_type not in spans.per_type_attrs:
                        spans.per_type_attrs[span_type] = set(attr_names)
                    else:
                        spans.per_type_attrs[span_type].intersection_update(attr_names)
                    spans.per_type_any_attrs.setdefault(span_type, set()).update(attr_names)

            log = sample.get("log")
            if log:
                event_name = log.get("event_name", "")
                if event_name.startswith("gen_ai."):
                    signals.events[event_name] = signals.events.get(event_name, 0) + 1
                    attr_names = _attribute_names(log, include_attr)
                    if event_name not in signals.event_attrs:
                        signals.event_attrs[event_name] = set(attr_names)
                    else:
                        signals.event_attrs[event_name].intersection_update(attr_names)
                    signals.event_any_attrs.setdefault(event_name, set()).update(attr_names)

            metric = sample.get("metric")
            if metric:
                metric_name = metric.get("name", "")
                if not isinstance(metric_name, str) or not metric_name:
                    _LOGGER.warning("Skipping metric with invalid name: %r", metric_name)
                    continue

                observations = _metric_data_points(metric)
                if observations is None or not observations:
                    continue

                metric_attrs_by_type: dict[str, set[str]] = {}
                metric_any_attrs_by_type: dict[str, set[str]] = {}
                for observation in observations:
                    metric_attrs = _attributes_by_name(observation, include_attr)
                    attr_names = set(metric_attrs)
                    for metric_type in classify_metric(metric_name, metric_attrs):
                        if metric_type not in metric_attrs_by_type:
                            metric_attrs_by_type[metric_type] = set(attr_names)
                        else:
                            metric_attrs_by_type[metric_type].intersection_update(attr_names)
                        metric_any_attrs_by_type.setdefault(metric_type, set()).update(attr_names)

                if not metric_attrs_by_type:
                    if metric_name.startswith("gen_ai."):
                        _LOGGER.warning("Skipping untracked GenAI metric: %s", metric_name)
                    continue

                for metric_type, attr_names in metric_attrs_by_type.items():
                    signals.metrics[metric_type] = signals.metrics.get(metric_type, 0) + 1
                    if metric_type not in signals.metric_attrs:
                        signals.metric_attrs[metric_type] = set(attr_names)
                    else:
                        signals.metric_attrs[metric_type].intersection_update(attr_names)
                    signals.metric_any_attrs.setdefault(metric_type, set()).update(
                        metric_any_attrs_by_type.get(metric_type, set())
                    )

    return spans, signals


# ── Result types and parsing ───────────────────────────────────────


@dataclass
class ObservedTelemetry:
    attrs: dict[str, int] = field(default_factory=dict)
    non_registry_attrs: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, int] = field(default_factory=dict)
    events: dict[str, int] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    library: str
    statistics: dict | None
    observed: ObservedTelemetry = field(default_factory=ObservedTelemetry)
    spans: SpanClassification = field(default_factory=SpanClassification)
    detected: DetectedSignals = field(default_factory=DetectedSignals)


def try_parse_json(content: str, source: Path | str | None = None) -> list[dict]:
    """Parse JSON content, handling a single object, array, or JSONL."""
    objects: list[dict] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        objects.extend(data)
        return objects
    if isinstance(data, dict):
        objects.append(data)
        return objects

    location = f" in {source}" if source else ""
    for line_no, raw_line in enumerate(content.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            objects.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"malformed JSON on line {line_no}{location}: {e.msg}") from e

    return objects


def merge_signal_counts(
    statistics_counts: dict[str, int],
    detected_counts: dict[str, int],
) -> dict[str, int]:
    """Merge statistic-derived and sample-derived signal counts.

    Element-wise max across both inputs.
    """
    merged = dict(statistics_counts)
    for name, count in detected_counts.items():
        merged[name] = max(merged.get(name, 0), count)
    return merged


def _non_zero_counts(statistics: dict | None, key: str) -> dict[str, int]:
    if not statistics:
        return {}
    return {name: count for name, count in statistics.get(key, {}).items() if count > 0}


def _extract_statistics(all_objects: list[dict]) -> dict | None:
    statistics = None
    for obj in all_objects:
        if not isinstance(obj, dict):
            continue
        if "statistics" in obj and isinstance(obj["statistics"], dict):
            statistics = obj["statistics"]
            continue
        if "registry_coverage" in obj or "advice_level_counts" in obj:
            statistics = obj
    return statistics


def _supplement_detected_from_statistics(
    detected_counts: dict[str, int],
    statistics: dict | None,
    statistics_key: str,
    signal_prefix: str,
) -> dict[str, int]:
    """Supplement sample-derived signal counts with statistics-only observations."""
    merged = dict(detected_counts)
    if not statistics:
        return merged

    for signal_name, count in statistics.get(statistics_key, {}).items():
        if count <= 0 or not signal_name.startswith(signal_prefix):
            continue
        if count > merged.get(signal_name, 0):
            merged[signal_name] = count
    return merged


def _load_result_objects(result_dir: Path) -> list[dict]:
    """Load and parse all JSON result objects from a Weaver result directory."""
    all_objects: list[dict] = []
    for json_file in sorted(result_dir.glob("**/*.json")):
        all_objects.extend(try_parse_json(json_file.read_text(encoding="utf-8"), json_file))
    return all_objects


def _iter_attribute_advice(attribute: dict[str, object]) -> Iterable[dict[str, object]]:
    live_check_result = attribute.get("live_check_result")
    if not isinstance(live_check_result, dict):
        return

    for advice in live_check_result.get("all_advice", []):
        if isinstance(advice, dict):
            yield advice


def _attribute_blocks_presence(
    attribute: dict[str, object],
) -> bool:
    for advice in _iter_attribute_advice(attribute):
        if advice.get("id") == "not_stable":
            continue
        if advice.get("id") == "type_mismatch":
            return True
    return False


def _attribute_counts_as_present(
    attribute: dict[str, object],
) -> bool:
    return not _attribute_blocks_presence(attribute)


def _iter_attribute_records(node: object) -> Iterable[dict[str, object]]:
    if isinstance(node, dict):
        attrs = node.get("attributes")
        if isinstance(attrs, list):
            for attr in attrs:
                if isinstance(attr, dict):
                    yield attr
        for value in node.values():
            if isinstance(value, (dict, list)):
                yield from _iter_attribute_records(value)
        return

    if isinstance(node, list):
        for value in node:
            if isinstance(value, (dict, list)):
                yield from _iter_attribute_records(value)


def _observed_registry_attribute_counts_from_samples(
    all_objects: list[dict],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in all_objects:
        if not isinstance(obj, dict):
            continue
        for sample in obj.get("samples", []):
            for attr in _iter_attribute_records(sample):
                name = attr.get("name")
                if not isinstance(name, str) or not name:
                    continue
                if not _attribute_counts_as_present(attr):
                    continue
                counts[name] = counts.get(name, 0) + 1
    return counts


def _observed_telemetry_from_statistics(
    statistics: dict | None,
    all_objects: list[dict],
) -> ObservedTelemetry:
    """Build observed telemetry counts from Weaver summary statistics."""
    seen_events = _non_zero_counts(statistics, "seen_registry_events")

    seen_metrics = _non_zero_counts(statistics, "seen_registry_metrics")

    seen_registry_attrs = _non_zero_counts(statistics, "seen_registry_attributes")
    sample_registry_attrs = _observed_registry_attribute_counts_from_samples(all_objects)
    if sample_registry_attrs:
        if seen_registry_attrs:
            seen_registry_attrs = {
                name: sample_registry_attrs.get(name, 0)
                for name in seen_registry_attrs
                if sample_registry_attrs.get(name, 0) > 0
            }
        else:
            seen_registry_attrs = {name: count for name, count in sample_registry_attrs.items() if count > 0}

    return ObservedTelemetry(
        attrs=seen_registry_attrs,
        non_registry_attrs=_non_zero_counts(statistics, "seen_non_registry_attributes"),
        events=seen_events,
        metrics=seen_metrics,
    )


def _detected_signals_from_samples(
    all_objects: list[dict],
    statistics: dict | None,
    classify_span: ClassifySpan,
    classify_metric: ClassifyMetric,
) -> tuple[SpanClassification, DetectedSignals]:
    """Classify spans and supplement detected signal counts from statistics."""
    span_classification, detected = _summarize_samples(
        all_objects,
        classify_span,
        classify_metric,
        include_attr=_attribute_counts_as_present,
    )
    stats = statistics or {}
    detected.events = _supplement_detected_from_statistics(
        detected.events,
        stats,
        "seen_registry_events",
        "gen_ai.",
    )
    detected.metrics = _supplement_detected_from_statistics(
        detected.metrics,
        stats,
        "seen_registry_metrics",
        "gen_ai.",
    )
    return span_classification, detected


def parse_result_dir(
    result_dir: Path,
    library: str,
    classify_span: ClassifySpan,
    classify_metric: ClassifyMetric,
) -> ScenarioResult | None:
    """Parse a single library's Weaver output directory into a ScenarioResult."""
    if not result_dir.is_dir():
        return None

    all_objects = _load_result_objects(result_dir)
    statistics = _extract_statistics(all_objects)
    observed = _observed_telemetry_from_statistics(statistics, all_objects)
    span_classification, detected = _detected_signals_from_samples(
        all_objects, statistics, classify_span, classify_metric
    )
    return ScenarioResult(
        library=library,
        statistics=statistics,
        observed=observed,
        spans=span_classification,
        detected=detected,
    )
