from __future__ import annotations

import json
from pathlib import Path

from semconv_genai.data_files import attr_names
from semconv_genai.semconv_model import span_refinement_specs


def _counts_as_present(attribute: dict[str, object]) -> bool:
    live_check_result = attribute.get("live_check_result")
    if not isinstance(live_check_result, dict):
        return True
    all_advice = live_check_result.get("all_advice")
    if not isinstance(all_advice, list):
        return True
    return not any(isinstance(advice, dict) and advice.get("id") == "type_mismatch" for advice in all_advice)


def _observed_spans(report_dir: Path):
    for path in sorted(report_dir.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for sample in report.get("samples", []):
            span = sample.get("span")
            if not isinstance(span, dict):
                continue
            attributes = {
                attribute["name"]: attribute.get("value")
                for attribute in span.get("attributes", [])
                if (
                    isinstance(attribute, dict)
                    and isinstance(attribute.get("name"), str)
                    and _counts_as_present(attribute)
                )
            }
            yield span.get("kind"), attributes


def collect_span_refinement_coverage(report_dir: Path) -> dict[str, list[str]]:
    if not report_dir.is_dir():
        raise RuntimeError(f"Missing Weaver report directory: {report_dir}")

    collected: dict[str, set[str]] = {}
    for span_kind, attributes in _observed_spans(report_dir):
        for spec in span_refinement_specs().values():
            if span_kind != spec.span_kind:
                continue
            if attributes.get("gen_ai.operation.name") != spec.operation_name:
                continue
            if attributes.get(spec.discriminator) is None:
                continue
            present = set(attr_names(spec)) & attributes.keys()
            collected.setdefault(spec.registry_id, set()).update(present)

    return {registry_id: sorted(attributes) for registry_id, attributes in sorted(collected.items())}


def update_span_refinement_coverage(
    scenario_dir: Path,
    *,
    data_file: Path | None = None,
    report_dir: Path | None = None,
) -> None:
    data_file = data_file or scenario_dir / "data.json"
    if not data_file.is_file():
        raise RuntimeError(f"Missing conformance data file: {data_file}")

    data = json.loads(data_file.read_text(encoding="utf-8"))
    data["span_refinements"] = collect_span_refinement_coverage(
        report_dir or scenario_dir / "output" / "weaver-reports"
    )
    data_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
