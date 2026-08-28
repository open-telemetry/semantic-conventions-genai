"""The conformance runner this repository's scenarios run under.

The runner, the GenAI advice policies and the mock LLM server live in
`open-telemetry/semantic-conventions-conformance
<https://github.com/open-telemetry/semantic-conventions-conformance>`_. Nothing
of them is vendored here: the checkout is fetched at the ``CONFORMANCE_REF``
pinned in the repository-root ``versions.env`` and its ``genai-conformance``
project is synced into a uv environment beside it.

That package pins a *released* GenAI registry, which is not what a change to
this repository should be checked against, so every run passes ``--registry
model/``. An overriding registry replaces the pin outright: it is what weaver
validates against, what the coverage in ``data.json`` is reduced against, and
where the content schemas are read from, and the pin is never fetched.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from semconv_genai import MODEL_ROOT, REFERENCE_ROOT, SEMCONV_ROOT
from semconv_genai.versions import require_pin
from semconv_genai.weaver import ensure_weaver, path_from_env

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 120

# What the registry declares, per span type, event and metric, as weaver
# resolves it. A build artifact: derived from model/, cached, never committed.
COVERAGE_MODEL = REFERENCE_ROOT / ".cache" / "coverage-model.json"


def cache_root() -> Path:
    return path_from_env("CONFORMANCE_CACHE", Path.home() / ".cache" / "semconv-genai" / "conformance")


def _repo_slug(url: str) -> str:
    return url.removeprefix("https://github.com/").removesuffix(".git")


def checkout() -> Path:
    """Fetch the pinned conformance checkout into the cache and return it."""
    ref = require_pin("CONFORMANCE_REF")
    target = cache_root() / ref
    stamp = target / ".provisioned"
    if stamp.is_file():
        return target

    url = f"https://github.com/{_repo_slug(require_pin('CONFORMANCE_REPO_URL'))}/archive/{ref}.tar.gz"
    logger.info("Fetching the conformance runner from %s", url)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(target.parent), prefix="fetch-") as tmp:
        archive = Path(tmp) / "src.tar.gz"
        extracted = Path(tmp) / "extract"
        extracted.mkdir()
        try:
            with (
                urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response,
                archive.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
        except (TimeoutError, urllib.error.URLError) as e:
            raise RuntimeError(f"Failed to fetch the conformance runner from {url}: {e}") from e
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(extracted, filter="data")
        roots = [entry for entry in extracted.iterdir() if entry.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"Unexpected layout in the conformance archive: {[r.name for r in roots]}")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(roots[0]), str(target))
    stamp.touch()
    return target


def runner_project() -> Path:
    """The uv project providing ``genai-conformance`` and the mock server."""
    project = checkout() / "tools" / "gen-ai" / "runner"
    if not (project / "pyproject.toml").is_file():
        raise RuntimeError(f"The pinned conformance checkout has no runner project at {project}")
    return project


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "uv is required to run the conformance scenarios. "
            "Install it and retry: https://docs.astral.sh/uv/getting-started/installation/"
        )
    return uv


def _environment() -> dict[str, str]:
    """A clean environment with the pinned weaver ahead of anything on PATH."""
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH")}
    env["PATH"] = os.pathsep.join([str(ensure_weaver().parent), env.get("PATH", "")])
    return env


def _is_stale(model: Path) -> bool:
    """True unless ``model`` is there and newer than all source dependencies."""
    if not model.is_file():
        return True
    resolved_at = model.stat().st_mtime
    versions_env = SEMCONV_ROOT / "versions.env"
    if versions_env.is_file() and versions_env.stat().st_mtime > resolved_at:
        return True
    return any(source.stat().st_mtime > resolved_at for source in MODEL_ROOT.rglob("*") if source.is_file())


def coverage_model(output: Path = COVERAGE_MODEL) -> Path:
    """The coverage model for ``model/``, resolved if the cache is stale.

    The runner resolves the same thing for itself to reduce a run into
    ``data.json``; the reports read this one, so both are the registry's own
    resolution rather than two readings of it.
    """
    if not _is_stale(output):
        return output
    # Clear the stale model so the runner's resolver re-runs Weaver rather
    # than returning the existing file early.
    output.unlink(missing_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Resolving %s into %s", MODEL_ROOT, output)
    command = [
        _uv(),
        "run",
        "--project",
        str(runner_project()),
        "python",
        "-c",
        "import pathlib, sys; from opentelemetry.conformance import resolve_coverage_model; resolve_coverage_model(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))",
        str(MODEL_ROOT),
        str(output),
    ]
    subprocess.run(command, cwd=SEMCONV_ROOT, env=_environment(), check=True)
    return output


def run(directory: Path, *, report_only: bool, extra_args: list[str] | None = None) -> int:
    """Run one conformance directory's scenarios; return the runner's exit code."""
    command = [
        _uv(),
        "run",
        "--project",
        str(runner_project()),
        "genai-conformance",
        str(directory),
        "--registry",
        str(MODEL_ROOT),
    ]
    if report_only:
        command.append("--report-only")
    command.extend(extra_args or [])
    return subprocess.run(command, cwd=SEMCONV_ROOT, env=_environment(), check=False).returncode
