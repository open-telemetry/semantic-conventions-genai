"""Reduce conformance reports with span types newer than the pinned runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from genai_conformance import _coverage
from opentelemetry.conformance import load_coverage_model, semconv_coverage
from opentelemetry.conformance._spec import load_spec


def main() -> None:
    report_dir = Path(sys.argv[1])
    scenario_dir = Path(sys.argv[2])
    model_path = Path(sys.argv[3])

    _coverage._OPERATION_NAMES["gen_ai.apply_guardrail.client"] = {"apply_guardrail"}
    model = load_coverage_model(model_path)
    build_data = semconv_coverage(_coverage.classifier(model), lambda: model)
    print(json.dumps(build_data(report_dir, load_spec(scenario_dir))))


if __name__ == "__main__":
    main()
