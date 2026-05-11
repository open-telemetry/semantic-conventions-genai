"""What attributes each GenAI span, event, and metric type should have.

Attribute lists are derived from the YAML semconv model at ``model/gen-ai/``.
Only labels, op_names, and discriminator_attrs are maintained here.

Ordering convention: every attribute / signal list written to a committed
artifact (``scenarios/<lib>/data.json``, the generated status reports, the
README injection) is sorted alphabetically. Please preserve this when adding
new emitters -- downstream diffs and `git diff --exit-code` in CI rely on a
single deterministic order.
"""

from __future__ import annotations

import yaml

from semconv_genai import MODEL_ROOT
from semconv_genai.attribute_spec import AttributeSpec

# ── YAML model parsing ─────────────────────────────────────────────

_MODEL_DIR = MODEL_ROOT / "gen-ai"


def _load_groups() -> dict[str, dict]:
    """Load all source files under ``model/gen-ai/`` and return a unified
    lookup keyed by a synthetic id covering attribute groups, spans, and
    events.

    Spans are keyed by ``type:`` and events by ``name:``; we prepend
    ``span.`` / ``event.`` here so callers can address them with stable
    ids like ``span.gen_ai.inference.client``."""
    groups: dict[str, dict] = {}
    for path in sorted(_MODEL_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text("utf-8")) or {}
        for ag in doc.get("attribute_groups", []) or []:
            if "id" in ag:
                groups[ag["id"]] = ag
        for span in doc.get("spans", []) or []:
            if "type" in span:
                groups[f"span.{span['type']}"] = span
        for event in doc.get("events", []) or []:
            if "name" in event:
                groups[f"event.{event['name']}"] = event
    return groups


def _requirement_level_key(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and raw:
        return next(iter(raw))
    raise ValueError(f"Unsupported requirement_level value: {raw!r}")


def _resolve_attrs(groups: dict[str, dict], group_id: str) -> dict[str, str]:
    """Resolve the merged ref->requirement_level map for a group.

    Inheritance is expressed inline via ``- ref_group: <id>`` entries that
    may appear anywhere in the ``attributes:`` list. Later entries override
    earlier ones, mirroring Weaver's resolution order."""
    group = groups.get(group_id)
    if not group:
        return {}
    attrs: dict[str, str] = {}
    for entry in group.get("attributes", []) or []:
        if not isinstance(entry, dict):
            continue
        if "ref_group" in entry:
            attrs.update(_resolve_attrs(groups, entry["ref_group"]))
            continue
        ref = entry.get("ref")
        if not ref:
            continue
        level = entry.get("requirement_level")
        if level is not None:
            attrs[ref] = _requirement_level_key(level)
    return attrs


def _from_yaml(
    groups: dict[str, dict],
    group_id: str,
    *,
    label: str,
    op_names: frozenset[str] = frozenset(),
    discriminator_attrs: frozenset[str] = frozenset(),
) -> AttributeSpec:
    attrs = _resolve_attrs(groups, group_id)
    buckets: dict[str, list[str]] = {
        "required": [],
        "conditionally_required": [],
        "recommended": [],
        "opt_in": [],
    }
    for name, level in sorted(attrs.items()):
        buckets[level].append(name)
    return AttributeSpec(
        label=label,
        required=tuple(buckets["required"]),
        conditionally_required=tuple(buckets["conditionally_required"]),
        recommended=tuple(buckets["recommended"]),
        opt_in=tuple(buckets["opt_in"]),
        op_names=op_names,
        discriminator_attrs=discriminator_attrs,
    )


# ── Specs derived from the YAML model ──────────────────────────────

_groups = _load_groups()

SPAN_SPECS: dict[str, AttributeSpec] = {
    "inference": _from_yaml(
        _groups,
        "span.gen_ai.inference.client",
        label="Inference",
        op_names=frozenset({"chat", "generate_content", "text_completion"}),
    ),
    "embeddings": _from_yaml(
        _groups,
        "span.gen_ai.embeddings.client",
        label="Embeddings",
        op_names=frozenset({"embeddings"}),
        discriminator_attrs=frozenset(
            {
                "gen_ai.embeddings.dimension.count",
                "gen_ai.request.encoding_formats",
            }
        ),
    ),
    "retrieval": _from_yaml(
        _groups,
        "span.gen_ai.retrieval.client",
        label="Retrieval",
        op_names=frozenset({"retrieval"}),
        discriminator_attrs=frozenset({"gen_ai.data_source.id"}),
    ),
    "execute_tool": _from_yaml(
        _groups,
        "span.gen_ai.execute_tool.internal",
        label="Execute Tool",
        op_names=frozenset({"execute_tool"}),
        discriminator_attrs=frozenset(
            {
                "gen_ai.tool.call.id",
                "gen_ai.tool.name",
            }
        ),
    ),
    "create_agent": _from_yaml(
        _groups,
        "span.gen_ai.create_agent.client",
        label="Create Agent",
        op_names=frozenset({"create_agent"}),
        # Note: gen_ai.agent.{id,name} are shared with invoke_agent spans, so
        # they can't be used as presence-based fallbacks here.
    ),
    "invoke_agent_client": _from_yaml(
        _groups,
        "span.gen_ai.invoke_agent.client",
        label="Invoke Agent Client",
        op_names=frozenset({"invoke_agent"}),
        discriminator_attrs=frozenset({"gen_ai.agent.id", "gen_ai.agent.name"}),
    ),
    "invoke_agent_internal": _from_yaml(
        _groups,
        "span.gen_ai.invoke_agent.internal",
        label="Invoke Agent Internal",
        op_names=frozenset({"invoke_agent"}),
        discriminator_attrs=frozenset({"gen_ai.agent.id", "gen_ai.agent.name"}),
    ),
    "invoke_workflow": _from_yaml(
        _groups,
        "span.gen_ai.invoke_workflow.internal",
        label="Invoke Workflow",
        op_names=frozenset({"invoke_workflow"}),
        discriminator_attrs=frozenset({"gen_ai.workflow.name"}),
    ),
    "plan": _from_yaml(
        _groups,
        "span.gen_ai.plan.internal",
        label="Plan",
        op_names=frozenset({"plan"}),
    ),
}

EVENT_SPECS: dict[str, AttributeSpec] = {
    "gen_ai.client.inference.operation.details": _from_yaml(
        _groups,
        "event.gen_ai.client.inference.operation.details",
        label="Inference Operation Details",
    ),
    "gen_ai.evaluation.result": _from_yaml(
        _groups,
        "event.gen_ai.evaluation.result",
        label="Evaluation Result",
    ),
}

# No METRIC_SPECS yet: gen_ai.* metrics are deliberately omitted from the reference
# coverage matrix because the two non-streaming metrics
# (`gen_ai.client.operation.duration`, `gen_ai.client.token.usage`) are
# derivable from data already present on inference spans (span start/end and
# `gen_ai.usage.{input,output}_tokens`). Reference scenarios emit spans only.
