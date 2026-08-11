"""Discovery of the reference scenario directories under ``scenarios/``."""

from __future__ import annotations

from semconv_genai import REFERENCE_ROOT, SCENARIOS_DIR, reference_data_file


def list_reference_libraries() -> list[str]:
    """Every library slug that has a runnable conformance directory."""
    return [
        path.name
        for path in sorted(SCENARIOS_DIR.iterdir())
        if path.is_dir() and (path / "conformance.yaml").is_file() and (path / "scenario.py").is_file()
    ]


def build_reference_scenario_matrix() -> dict[str, list[dict[str, str]]]:
    return {
        "scenario": [
            {
                "lib": library,
                "data": reference_data_file(library).relative_to(REFERENCE_ROOT).as_posix(),
            }
            for library in list_reference_libraries()
        ]
    }
