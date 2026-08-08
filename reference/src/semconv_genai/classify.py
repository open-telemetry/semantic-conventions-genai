"""GenAI signal classification: map observed telemetry to declared GenAI types."""

from __future__ import annotations

from .semconv_model import METRIC_SPECS, SPAN_SPECS


def _has_any_attr(attrs: dict[str, object], *names: str) -> bool:
    return any(attrs.get(name) is not None for name in names)


def _matches_spec(op_name: str, attrs: dict[str, object], span_type_key: str) -> bool:
    """True if a span matches the span type declared in SPAN_SPECS."""
    spec = SPAN_SPECS[span_type_key]
    if op_name and op_name in spec.op_names:
        return True
    if spec.discriminator_attrs and _has_any_attr(attrs, *spec.discriminator_attrs):
        # create_agent and plan share their attribute set with invoke_agent
        # (gen_ai.agent.{id,name}); a span explicitly marked as one of those
        # operations never counts as invoke_agent.
        return not (span_type_key.startswith("invoke_agent") and op_name in {"create_agent", "plan"})
    return False


def classify_span(span_name: str, span_kind: str, span_attrs: dict[str, object]) -> set[str]:
    """Classify a span into GenAI span types using model-backed discriminators.

    ``span_name`` is accepted to match the shared ``ClassifySpan`` signature
    but is not used. ``span_kind`` disambiguates the two ``invoke_agent`` span
    types; the rest of the classification is attribute-driven
    (``gen_ai.operation.name`` plus discriminator attrs).
    """
    del span_name  # unused; accepted for signature compatibility
    op_name = str(span_attrs.get("gen_ai.operation.name", "")).lower()
    detected = {key for key in SPAN_SPECS if _matches_spec(op_name, span_attrs, key)}

    # invoke_agent is represented as two span types (client vs internal) that
    # share op_name/discriminator_attrs; disambiguate by span kind.
    if "invoke_agent_client" in detected or "invoke_agent_internal" in detected:
        is_client_span = span_kind.lower() == "client"
        detected.discard("invoke_agent_client" if not is_client_span else "invoke_agent_internal")

    return detected


def classify_metric(metric_name: str, metric_attrs: dict[str, object]) -> set[str]:
    """Classify a metric data point into GenAI metric types."""
    del metric_attrs  # Metric identity is represented by the metric name.
    return {metric_name} if metric_name in METRIC_SPECS else set()
