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
# resolves it. Committed, and read by the report generation.
COVERAGE_MODEL = REFERENCE_ROOT / "coverage-model.json"


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


def resolve_coverage_model(output: Path = COVERAGE_MODEL) -> Path:
    """Resolve ``model/`` into the coverage model, the same way a run does.

    The runner resolves this for itself to reduce a run into ``data.json``;
    committing it as well is what lets the reports be built from the registry's
    own resolution without weaver or a scenario run.
    """
    script = checkout() / "tools" / "runner" / "src" / "opentelemetry" / "conformance" / "collect-coverage-model.sh"
    if not script.is_file():
        raise RuntimeError(f"The pinned conformance checkout has no {script.name}")
    subprocess.run([str(script), str(MODEL_ROOT), str(output)], cwd=SEMCONV_ROOT, env=_environment(), check=True)
    return output


def main() -> int:
    """Console-script entry point: refresh the committed coverage model."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Coverage model written to {resolve_coverage_model()}")
    return 0


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
