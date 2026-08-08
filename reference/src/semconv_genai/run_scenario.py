#!/usr/bin/env python3
"""Run the reference scenarios under the pinned conformance runner.

Each ``scenarios/<library>/`` is a conformance directory: a ``conformance.yaml``
saying how to run the scenario and what it must produce, and a committed
``data.json`` recording the attribute coverage a run achieved. The runner
starts the mock LLM server and weaver live-check, runs the scenario against
them, checks what it emitted, and rewrites ``data.json``.

Violations are reported as warnings by default -- the reference scenarios are
being brought under the runner and their gaps are not yet declared. Pass
``--strict`` to fail on them. A scenario that crashes or misses what its
``conformance.yaml`` declares fails either way.

Usage:
    run-scenario <library> [--strict] [runner-args...]
    run-scenario --all [--keep-going] [--strict] [runner-args...]
    run-scenario --print-ci-matrix
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from semconv_genai import conformance, reference_project_dir
from semconv_genai.scenarios import (
    build_reference_scenario_matrix,
    list_reference_libraries,
)

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        prog="run-scenario",
        description="Run reference scenarios under the pinned conformance runner.",
    )
    parser.add_argument("library", nargs="?", help="Library slug")
    parser.add_argument("--all", action="store_true", help="Run all reference scenarios")
    parser.add_argument("--keep-going", action="store_true", help="Continue after failures when using --all")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on semantic-convention violations instead of reporting them",
    )
    parser.add_argument(
        "--print-ci-matrix",
        action="store_true",
        help="Print CI matrix JSON for runnable reference scenarios",
    )
    args, extra = parser.parse_known_args(argv)

    if args.print_ci_matrix:
        if args.all or args.keep_going or args.library or extra:
            parser.error("--print-ci-matrix cannot be combined with scenario execution arguments")
        return args, []

    if args.all and args.library:
        parser.error("library cannot be provided together with --all")
    if not args.all and not args.library:
        parser.error("library is required unless --all is provided")

    return args, extra


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    args, extra = _parse_args(sys.argv[1:] if argv is None else argv)

    libraries = list_reference_libraries()
    if not libraries:
        logger.error("No reference scenarios found.")
        return 1

    if args.print_ci_matrix:
        print(json.dumps(build_reference_scenario_matrix(), separators=(",", ":")))
        return 0

    if args.all:
        selected = libraries
        logger.info("Running all reference scenarios (%s)", len(selected))
    elif args.library not in libraries:
        logger.error("Unknown library: %s", args.library)
        print("Available libraries:", file=sys.stderr)
        for library in libraries:
            print(f"  {library}", file=sys.stderr)
        return 1
    else:
        selected = [args.library]

    failures: list[tuple[str, int]] = []
    for index, library in enumerate(selected, start=1):
        if args.all:
            logger.info("[%s/%s] %s", index, len(selected), library)
        try:
            exit_code = conformance.run(
                reference_project_dir(library),
                report_only=not args.strict,
                extra_args=extra,
            )
        except RuntimeError as e:
            # Fetching the runner, finding uv or installing weaver -- the
            # scenario never got to run, so say so rather than trace.
            logger.error("%s: %s", library, e)
            exit_code = 1
        if exit_code != 0:
            failures.append((library, exit_code))
            if not args.all or not args.keep_going:
                return exit_code

    if failures:
        logger.error("Failed reference scenarios:")
        for library, exit_code in failures:
            logger.error("  %s (exit %s)", library, exit_code)
        return failures[0][1] or 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
