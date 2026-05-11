#!/usr/bin/env python3
"""Report generation: README.md index and per-type detail pages.

Usage:
    uv run update-reports [--output FILE]
    python -m semconv_genai.report [--output FILE]

Builds deterministic markdown pages from committed scenarios/*/data.json files:
  - Injects a summary index between markers in README.md.
  - Writes one detail page per span/event type under reports/.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from semconv_genai import (
    REFERENCE_ROOT,
    reference_scenario_file,
)
from semconv_genai.attribute_spec import AttributeSpec, RequirementLevel
from semconv_genai.data_files import (
    EVENT_TYPE_ORDER,
    SPAN_TYPE_ORDER,
    ScenarioDataEntry,
    load_scenario_data_files,
)
from semconv_genai.semconv_model import (
    EVENT_SPECS,
    SPAN_SPECS,
)

# ── Report page generation ───────────────────────────────────────────


DISPLAY_HIDDEN_ATTRS = frozenset({"error.type"})
EMPTY_TABLE_VALUE = "(none)"

OUTPUT_FILE = REFERENCE_ROOT / "README.md"
REPORTS_DIR = REFERENCE_ROOT / "reports"
BEGIN_MARKER = "<!-- status:begin -->"
END_MARKER = "<!-- status:end -->"
LEVEL_ORDER = (
    RequirementLevel.REQUIRED,
    RequirementLevel.CONDITIONALLY_REQUIRED,
    RequirementLevel.RECOMMENDED,
    RequirementLevel.OPT_IN,
)
LEVEL_LABELS = {
    RequirementLevel.REQUIRED: "Required",
    RequirementLevel.CONDITIONALLY_REQUIRED: "Conditionally Required",
    RequirementLevel.RECOMMENDED: "Recommended",
    RequirementLevel.OPT_IN: "Opt-In",
}


def _spans_of(entry: ScenarioDataEntry) -> dict[str, dict[str, str]]:
    return entry.spans


def _events_of(entry: ScenarioDataEntry) -> dict[str, dict[str, str]]:
    return entry.events


# Relative paths from reports/ to the semantic convention doc page + anchor.
SEMCONV_DOC_LINKS: dict[str, str] = {
    "create_agent": "../../docs/gen-ai/gen-ai-agent-spans.md#create-agent-span",
    "invoke_agent_client": "../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-client-span",
    "invoke_agent_internal": "../../docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-internal-span",
    "invoke_workflow": "../../docs/gen-ai/gen-ai-agent-spans.md#invoke-workflow-span",
    "plan": "../../docs/gen-ai/gen-ai-agent-spans.md#plan-span",
    "inference": "../../docs/gen-ai/gen-ai-spans.md#inference",
    "embeddings": "../../docs/gen-ai/gen-ai-spans.md#embeddings",
    "retrieval": "../../docs/gen-ai/gen-ai-spans.md#retrievals",
    "execute_tool": "../../docs/gen-ai/gen-ai-spans.md#execute-tool-span",
    "gen_ai.client.inference.operation.details": "../../docs/gen-ai/gen-ai-events.md#event-gen_aiclientinferenceoperationdetails",
    "gen_ai.evaluation.result": "../../docs/gen-ai/gen-ai-events.md#event-gen_aievaluationresult",
}


def _entry_sort_key(entry: ScenarioDataEntry) -> tuple[str, str]:
    return (entry.library.lower(), entry.library)


def _table_escape(value: str) -> str:
    return value.replace("|", "\\|")


def _libraries_in_scope(entries: list[ScenarioDataEntry]) -> str:
    if not entries:
        return EMPTY_TABLE_VALUE
    return ", ".join(entry.library for entry in entries)


def _supporting_libraries(
    entries: list[ScenarioDataEntry],
    type_key: str,
    attr_name: str,
    by_signal: Callable[[ScenarioDataEntry], dict[str, dict[str, str]]],
) -> list[ScenarioDataEntry]:
    return [entry for entry in entries if by_signal(entry).get(type_key, {}).get(attr_name) == "present"]


def _library_reference_path(library: str, output_dir: Path) -> str:
    scenario_path = reference_scenario_file(library)
    return Path(os.path.relpath(scenario_path, output_dir)).as_posix()


def _supporting_library_refs(entries: list[ScenarioDataEntry]) -> str:
    """Return a comma-separated list of short reference-style library links.

    The `[lib]` tokens are resolved via link-reference definitions emitted
    once per page by ``_link_reference_block``.
    """
    if not entries:
        return EMPTY_TABLE_VALUE
    return ", ".join(f"[{entry.library}]" for entry in entries)


def _link_reference_block(libraries: set[str], output_dir: Path) -> list[str]:
    """Return `[lib]: path` link-reference definitions for every ``libraries`` entry."""
    if not libraries:
        return []
    return [f"[{lib}]: {_library_reference_path(lib, output_dir)}" for lib in sorted(libraries)]


def _render_signal_section(
    entries: list[ScenarioDataEntry],
    type_key: str,
    spec: AttributeSpec,
    output_dir: Path,
    signal_kind: str,
    by_signal: Callable[[ScenarioDataEntry], dict[str, dict[str, str]]],
) -> list[str]:
    lines = [f"# {spec.label} {signal_kind}", ""]
    doc_link = SEMCONV_DOC_LINKS.get(type_key)
    if doc_link:
        lines.append(f"> **[Semantic Convention]({doc_link})**")
        lines.append("")

    used_libraries: set[str] = set()
    for level in LEVEL_ORDER:
        attr_names = [a for a in spec.attrs_for_requirement_level(level) if a not in DISPLAY_HIDDEN_ATTRS]
        if not attr_names:
            continue

        lines.extend(
            [
                f"## {LEVEL_LABELS[level]}",
                "",
                "| Attribute | Supporting Libraries |",
                "| --- | --- |",
            ]
        )
        for attr_name in attr_names:
            libraries = _supporting_libraries(entries, type_key, attr_name, by_signal)
            used_libraries.update(entry.library for entry in libraries)
            lines.append(f"| {_table_escape(attr_name)} | {_supporting_library_refs(libraries)} |")
        lines.append("")

    ref_lines = _link_reference_block(used_libraries, output_dir)
    if ref_lines:
        lines.extend(ref_lines)
        lines.append("")

    return lines


def _type_slug(type_key: str) -> str:
    """Convert a type key like 'create_agent' or 'gen_ai.client.inference.operation.details' to a filename slug."""
    return type_key.replace("_", "-").replace(".", "-")


def _report_filename(type_key: str, signal_kind: str) -> str:
    return f"{_type_slug(type_key)}-{signal_kind}.md"


def _get_supporting_entries(
    entries: list[ScenarioDataEntry],
    type_key: str,
    spec: AttributeSpec,
    by_signal: Callable[[ScenarioDataEntry], dict[str, dict[str, str]]],
) -> list[ScenarioDataEntry]:
    """Return libraries that emit at least one required attribute for this signal type."""
    required_attrs = spec.attrs_for_requirement_level(RequirementLevel.REQUIRED)
    if not required_attrs:
        required_attrs = spec.attrs_for_requirement_level(RequirementLevel.CONDITIONALLY_REQUIRED)
    supporting = set()
    for attr_name in required_attrs:
        for entry in entries:
            if by_signal(entry).get(type_key, {}).get(attr_name) == "present":
                supporting.add(entry.library)
    return [e for e in entries if e.library in supporting]


def _generate_detail_page(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _library_dir_links(entries: list[ScenarioDataEntry]) -> str:
    if not entries:
        return EMPTY_TABLE_VALUE
    return ", ".join(e.library for e in entries)


def generate_index_markdown(
    test_data_entries: list[ScenarioDataEntry],
) -> str:
    entries = sorted(test_data_entries, key=_entry_sort_key)
    lines = [
        "",
        "### Spans",
        "",
        "| Span | Libraries |",
        "| --- | --- |",
    ]

    for span_type in SPAN_TYPE_ORDER:
        spec = SPAN_SPECS[span_type]
        filename = _report_filename(span_type, "span")
        supporting = _get_supporting_entries(entries, span_type, spec, _spans_of)
        lines.append(f"| [{spec.label}](reports/{filename}) | {_library_dir_links(supporting)} |")

    lines.extend(
        [
            "",
            "### Events",
            "",
            "| Event | Libraries |",
            "| --- | --- |",
        ]
    )

    for event_type in EVENT_TYPE_ORDER:
        spec = EVENT_SPECS[event_type]
        filename = _report_filename(event_type, "event")
        supporting = _get_supporting_entries(entries, event_type, spec, _events_of)
        lines.append(f"| [{spec.label}](reports/{filename}) | {_library_dir_links(supporting)} |")

    lines.append("")
    return "\n".join(lines)


def write_report_pages(output_dir: Path) -> None:
    entries = sorted(load_scenario_data_files(), key=_entry_sort_key)
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for span_type in SPAN_TYPE_ORDER:
        spec = SPAN_SPECS[span_type]
        legacy_page_path = reports_dir / f"{_type_slug(span_type)}.md"
        if legacy_page_path.exists():
            legacy_page_path.unlink()

        page_path = reports_dir / _report_filename(span_type, "span")
        page_lines = _render_signal_section(entries, span_type, spec, reports_dir, "Span", _spans_of)
        page_path.write_text(_generate_detail_page(page_lines), encoding="utf-8")

    for event_type in EVENT_TYPE_ORDER:
        spec = EVENT_SPECS[event_type]
        legacy_page_path = reports_dir / f"{_type_slug(event_type)}.md"
        if legacy_page_path.exists():
            legacy_page_path.unlink()

        page_path = reports_dir / _report_filename(event_type, "event")
        page_lines = _render_signal_section(entries, event_type, spec, reports_dir, "Event", _events_of)
        page_path.write_text(_generate_detail_page(page_lines), encoding="utf-8")


def write_status_report(output_file: Path) -> None:
    output_dir = output_file.parent

    # Generate detail pages
    write_report_pages(output_dir)

    # Inject index into README.md
    content = output_file.read_text(encoding="utf-8")
    begin_idx = content.find(BEGIN_MARKER)
    end_idx = content.find(END_MARKER)
    if begin_idx == -1 or end_idx == -1:
        raise ValueError(f"{output_file} is missing {BEGIN_MARKER} / {END_MARKER} markers")

    generated = generate_index_markdown(load_scenario_data_files())
    new_content = content[: begin_idx + len(BEGIN_MARKER)] + generated + content[end_idx:]
    output_file.write_text(new_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate checked-in markdown status report")
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help="Markdown file to write (default: reference/README.md)",
    )
    args = parser.parse_args()

    output_file = Path(args.output)
    write_status_report(output_file)
    print(f"Status report written to {output_file}")


if __name__ == "__main__":
    main()
