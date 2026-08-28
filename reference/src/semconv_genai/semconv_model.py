"""What attributes each GenAI span, event, and metric type declares.

Read from the coverage model: weaver's own resolution of ``model/``, and the
same view the conformance runner reduces a run against, so the reports and
``data.json`` can never disagree about what a signal declares. It is a build
artifact, resolved into ``reference/.cache/`` whenever ``model/`` is newer.

Resolving it shells out to weaver and may fetch the conformance checkout, so
the specs are built on first use rather than at import: importing this module
does no work and needs no network.

Only the display labels are maintained here.

Ordering convention: every attribute / signal list written to a committed
artifact (``scenarios/<lib>/data.json``, the generated status reports, the
README injection) is sorted alphabetically. Please preserve this when adding
new emitters -- downstream diffs and `git diff --exit-code` in CI rely on a
single deterministic order.
"""

from __future__ import annotations

import json
from functools import cache

from semconv_genai import MODEL_ROOT
from semconv_genai.attribute_spec import AttributeSpec
from semconv_genai.conformance import coverage_model

# The signals the reports cover, as {report key: (registry name, label)}. A
# registry signal absent from these is still resolved into the coverage model
# and recorded in data.json; it just has no report page.
_SPANS = {
    "inference": ("gen_ai.inference.client", "Inference"),
    "embeddings": ("gen_ai.embeddings.client", "Embeddings"),
    "retrieval": ("gen_ai.retrieval.client", "Retrieval"),
    "fetch_response": ("gen_ai.fetch_response.client", "Fetch Response"),
    "memory": ("gen_ai.memory.client", "Memory"),
    "execute_tool": ("gen_ai.execute_tool.internal", "Execute Tool"),
    "create_agent": ("gen_ai.create_agent.client", "Create Agent"),
    "invoke_agent_client": ("gen_ai.invoke_agent.client", "Invoke Agent Client"),
    "invoke_agent_internal": ("gen_ai.invoke_agent.internal", "Invoke Agent Internal"),
    "invoke_workflow": ("gen_ai.invoke_workflow.internal", "Invoke Workflow"),
    "plan": ("gen_ai.plan.internal", "Plan"),
}

_EVENTS = {
    "gen_ai.client.inference.operation.details": "Inference Operation Details",
    "gen_ai.evaluation.result": "Evaluation Result",
}

# `gen_ai.client.operation.duration` and `gen_ai.client.token.usage` are a
# single-span read, unlike the `invoke_agent` counters below, which need each
# call attributed to exactly one invocation across the call tree (#336). They
# are tracked here because agent-framework and anthropic emit them; this list
# records what the reference scenarios emit, not what instrumentations should emit.
_METRICS = {
    "gen_ai.client.token.usage": "Client Token Usage",
    "gen_ai.client.operation.duration": "Client Operation Duration",
    "gen_ai.invoke_agent.inference_calls": "Invoke Agent Inference Calls",
    "gen_ai.invoke_agent.tool_calls": "Invoke Agent Tool Calls",
}

_ENTITIES = {
    "gen_ai.main_agent": "Main Agent",
}


def _spec(model: dict[str, dict], kind: str, registry_id: str, label: str) -> AttributeSpec:
    declared = model.get(kind, {}).get(registry_id)
    if declared is None:
        raise RuntimeError(f"The coverage model declares no {kind[:-1]} {registry_id!r}; is it still in model/?")
    buckets: dict[str, list[str]] = {
        "required": [],
        "conditionally_required": [],
        "recommended": [],
        "opt_in": [],
    }
    for name, level in sorted(declared["attributes"].items()):
        # A level carrying a condition is written `<level>_conditional`; the
        # reports bucket by the level itself.
        buckets[level.removesuffix("_conditional")].append(name)
    return AttributeSpec(
        label=label,
        required=tuple(buckets["required"]),
        conditionally_required=tuple(buckets["conditionally_required"]),
        recommended=tuple(buckets["recommended"]),
        opt_in=tuple(buckets["opt_in"]),
        registry_id=registry_id,
    )


def _entity_spec_from_yaml(registry_id: str, label: str) -> AttributeSpec:
    """Fallback parser for entity definitions directly from model/ YAML files.

    Used when the conformance runner's coverage model does not yet include entities.
    """
    entities_file = MODEL_ROOT / "gen-ai" / "entities.yaml"
    if not entities_file.is_file():
        return AttributeSpec(
            label=label,
            required=(),
            conditionally_required=(),
            recommended=(),
            opt_in=(),
            registry_id=registry_id,
        )

    lines = entities_file.read_text("utf-8").splitlines()
    in_entity = False
    in_section = None
    buckets: dict[str, list[str]] = {
        "required": [],
        "conditionally_required": [],
        "recommended": [],
        "opt_in": [],
    }
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("- type:"):
            entity_type = line.split(":", 1)[1].strip()
            in_entity = entity_type == registry_id
            in_section = None
            continue
        if not in_entity:
            continue
        if line == "identity:":
            in_section = "identity"
            continue
        if line == "description:":
            in_section = "description"
            continue
        if not raw_line.startswith(" ") and ":" in line:
            in_section = None

        if in_section == "identity" and line.startswith("- ref:"):
            ref = line.split(":", 1)[1].strip()
            buckets["required"].append(ref)
        elif in_section == "description" and line.startswith("- ref:"):
            ref = line.split(":", 1)[1].strip()
            buckets["recommended"].append(ref)

    return AttributeSpec(
        label=label,
        required=tuple(sorted(buckets["required"])),
        conditionally_required=tuple(sorted(buckets["conditionally_required"])),
        recommended=tuple(sorted(buckets["recommended"])),
        opt_in=tuple(sorted(buckets["opt_in"])),
        registry_id=registry_id,
    )


@cache
def _model() -> dict[str, dict]:
    return json.loads(coverage_model().read_text(encoding="utf-8"))


@cache
def span_specs() -> dict[str, AttributeSpec]:
    model = _model()
    return {key: _spec(model, "spans", registry_id, label) for key, (registry_id, label) in _SPANS.items()}


@cache
def event_specs() -> dict[str, AttributeSpec]:
    model = _model()
    return {name: _spec(model, "events", name, label) for name, label in _EVENTS.items()}


@cache
def metric_specs() -> dict[str, AttributeSpec]:
    model = _model()
    return {name: _spec(model, "metrics", name, label) for name, label in _METRICS.items()}


def _entity_spec(model: dict[str, dict], registry_id: str, label: str) -> AttributeSpec:
    declared = model.get("entities", {}).get(registry_id)
    if declared is None:
        raise RuntimeError(f"The coverage model declares no entity {registry_id!r}; is it still in model/?")
    buckets: dict[str, list[str]] = {
        "required": [],
        "conditionally_required": [],
        "recommended": [],
        "opt_in": [],
    }
    if "attributes" in declared:
        for name, level in sorted(declared["attributes"].items()):
            buckets[level.removesuffix("_conditional")].append(name)
    else:
        for section in declared.values():
            if isinstance(section, dict):
                for name, level in sorted(section.items()):
                    buckets[level.removesuffix("_conditional")].append(name)
    return AttributeSpec(
        label=label,
        required=tuple(sorted(buckets["required"])),
        conditionally_required=tuple(sorted(buckets["conditionally_required"])),
        recommended=tuple(sorted(buckets["recommended"])),
        opt_in=tuple(sorted(buckets["opt_in"])),
        registry_id=registry_id,
    )


@cache
def entity_specs() -> dict[str, AttributeSpec]:
    model = _model()
    entities_model = model.get("entities", {})
    specs: dict[str, AttributeSpec] = {}
    for name, label in _ENTITIES.items():
        if name in entities_model:
            specs[name] = _entity_spec(model, name, label)
        else:
            specs[name] = _entity_spec_from_yaml(name, label)
    return specs
