"""End-to-end live-check pipeline for one reference library.

Runs, in order:

  1. ``ensure_python_scenario_env`` -- prepare the library's uv env.
  2. ``start_mock_server`` -- shared mock LLM server (caller manages lifetime).
  3. Weaver ``registry live-check`` -- receives OTel telemetry via gRPC.
  4. The library's ``scenario.py`` under its uv env.
  5. Stop Weaver, parse its JSON output, and write ``scenarios/<lib>/data.json``.

Public surface used by the CLI:

  - ``RunScenarioError`` -- raised for any scenario-level failure.
  - ``MOCK_SERVER_PORT``, ``start_mock_server`` -- shared mock server.
  - ``stop_process`` -- terminate the mock server when the CLI is done.
  - ``run_one_library`` -- run the full pipeline for a single library.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

from semconv_genai import (
    REFERENCE_ROOT,
    SEMCONV_ROOT,
    reference_results_dir,
)
from semconv_genai.classify import classify_span
from semconv_genai.data_files import write_generated_scenario_data
from semconv_genai.parse_results import parse_result_dir
from semconv_genai.uv_env import (
    ensure_python_scenario_env,
    run_reference_scenario,
)
from semconv_genai.weaver import ensure_weaver

logger = logging.getLogger(__name__)


MOCK_SERVER_PORT = 8080
WEAVER_INACTIVITY_TIMEOUT_SECONDS = 60


class WeaverPorts(NamedTuple):
    """The pair of loopback TCP ports used by one Weaver live-check instance."""

    grpc: int
    admin: int


class RunScenarioError(Exception):
    def __init__(
        self,
        message: str,
        exit_code: int = 1,
        show_available_scenarios: bool = False,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.show_available_scenarios = show_available_scenarios


def _allocate_free_tcp_ports(count: int) -> list[int]:
    """Ask the OS for unused loopback TCP ports to reduce collisions in CI."""
    sockets: list[socket.socket] = []
    try:
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def _prepare_results_dir(result_dir: Path) -> None:
    """Ensure the result directory starts empty for a fresh Weaver run."""
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)


def is_healthy(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
    except (OSError, urllib.error.URLError, TimeoutError):
        # Server not yet listening, or mid-restart; caller retries.
        return False
    return True


def wait_for_health(url: str, timeout: int, label: str, proc: subprocess.Popen | None = None) -> None:
    for i in range(1, timeout + 1):
        if is_healthy(url):
            logger.info("%s ready after %ss", label, i)
            return
        if proc and proc.poll() is not None:
            raise RunScenarioError(f"{label} process died during startup")
        time.sleep(1)
    raise RunScenarioError(f"{label} failed to become ready after {timeout}s")


def start_mock_server(mock_url: str) -> subprocess.Popen | None:
    health_url = f"{mock_url}/health"
    if is_healthy(health_url):
        logger.info("Mock server already running on port %s", MOCK_SERVER_PORT)
        return None

    logger.info("Starting mock server on port %s", MOCK_SERVER_PORT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "semconv_genai.mock_server",
            "--host",
            "127.0.0.1",
            "--port",
            str(MOCK_SERVER_PORT),
        ],
        cwd=REFERENCE_ROOT,
    )
    wait_for_health(health_url, 30, "Mock server", proc)
    return proc


def _build_weaver_command(
    weaver_bin: Path,
    result_dir: Path,
    extra_weaver_args: list[str],
    ports: WeaverPorts,
    registry: str,
) -> list[str]:
    command = [str(weaver_bin), "registry", "live-check"]
    if registry:
        command.extend(["-r", registry])
    command.extend(
        [
            "--format",
            "json",
            "--output",
            str(result_dir),
            "--otlp-grpc-port",
            str(ports.grpc),
            "--admin-port",
            str(ports.admin),
            "--inactivity-timeout",
            str(WEAVER_INACTIVITY_TIMEOUT_SECONDS),
        ]
    )
    command.extend(extra_weaver_args)
    return command


def _stop_weaver(admin_port: int, weaver_proc: subprocess.Popen) -> int:
    # Give Weaver up to 1s to exit on its own (e.g. via --inactivity-timeout)
    # before we force a stop. wait() returns immediately if it's already gone.
    try:
        return weaver_proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    stop_url = f"http://127.0.0.1:{admin_port}/stop"
    try:
        urllib.request.urlopen(
            urllib.request.Request(stop_url, method="POST"),
            timeout=5,
        )
    except (OSError, urllib.error.URLError, TimeoutError) as e:
        logger.info("Weaver admin /stop did not respond (%s); terminating instead.", e)
        weaver_proc.terminate()
    return weaver_proc.wait()


def _build_scenario_environment(mock_url: str, weaver_port: int) -> dict[str, str]:
    weaver_endpoint = f"http://127.0.0.1:{weaver_port}"
    caller_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if caller_endpoint and caller_endpoint != weaver_endpoint:
        logger.warning(
            "Overriding OTEL_EXPORTER_OTLP_ENDPOINT=%s with %s for the scenario run.",
            caller_endpoint,
            weaver_endpoint,
        )
    return {
        **os.environ,
        "MOCK_LLM_URL": mock_url,
        "OTEL_EXPORTER_OTLP_ENDPOINT": weaver_endpoint,
    }


def stop_process(proc: subprocess.Popen | None, label: str) -> None:
    if proc and proc.poll() is None:
        logger.info("Stopping %s (PID %s)...", label, proc.pid)
        proc.terminate()
        proc.wait()


def _validate_weaver_output(
    library: str,
    scenario_results_dir: Path,
    weaver_exit: int,
    has_weaver_stats: bool,
) -> None:
    """Raise if Weaver output is missing or unusable."""
    if not any(scenario_results_dir.glob("**/*.json")):
        raise RunScenarioError(
            f"Weaver produced no JSON output for scenario: {library}",
        )

    if weaver_exit != 0 and not has_weaver_stats:
        raise RunScenarioError(
            "Weaver exited non-zero before writing statistics.",
            exit_code=weaver_exit or 1,
        )
    if weaver_exit != 0:
        logger.warning(
            "Weaver returned a non-zero exit code because violations were reported; continuing with captured statistics.",
        )


def run_one_library(
    library: str,
    extra_weaver_args: list[str],
    registry: str,
    mock_url: str,
) -> None:
    """Run the full live-check pipeline for one reference library."""
    ensure_python_scenario_env(library)
    ports = WeaverPorts(*_allocate_free_tcp_ports(2))

    scenario_results_dir = reference_results_dir(library).resolve()
    _prepare_results_dir(scenario_results_dir)

    logger.info(
        "Starting weaver live-check for: %s (ports %s/%s)",
        library,
        ports.grpc,
        ports.admin,
    )
    weaver_cmd = _build_weaver_command(
        ensure_weaver(),
        scenario_results_dir,
        extra_weaver_args,
        ports,
        registry,
    )
    # Run weaver from the repo root so relative `registry_path` entries in
    # `model/manifest.yaml` resolve
    # consistently regardless of where this Python process was launched.
    weaver_proc: subprocess.Popen | None = subprocess.Popen(weaver_cmd, cwd=SEMCONV_ROOT)

    try:
        logger.info("Waiting for weaver to be ready...")
        wait_for_health(f"http://localhost:{ports.admin}/health", 60, "Weaver", weaver_proc)

        scenario_env = _build_scenario_environment(mock_url, ports.grpc)
        logger.info("Running scenario: %s", library)
        try:
            exit_code = run_reference_scenario(library, scenario_env)
        except FileNotFoundError as e:
            raise RunScenarioError(
                f"Could not find scenario '{library}'",
                show_available_scenarios=True,
            ) from e

        assert weaver_proc is not None  # narrow for type-checker; only set to None below
        weaver_exit = _stop_weaver(ports.admin, weaver_proc)
        weaver_proc = None
        logger.info("Weaver exit code: %s", weaver_exit)
        logger.info("Results in: %s", scenario_results_dir)
        fresh_result = parse_result_dir(scenario_results_dir, library, classify_span)
        if exit_code != 0:
            raise RunScenarioError(
                f"Scenario exited with code {exit_code}.",
                exit_code=exit_code or 1,
            )

        has_weaver_stats = fresh_result is not None and fresh_result.statistics is not None
        _validate_weaver_output(library, scenario_results_dir, weaver_exit, has_weaver_stats)

        logger.info("Updating scenario data file")
        try:
            result_path = write_generated_scenario_data(library)
        except ValueError as e:
            raise RunScenarioError(str(e)) from e
        logger.info("Updated %s", result_path)
    finally:
        stop_process(weaver_proc, "weaver")
