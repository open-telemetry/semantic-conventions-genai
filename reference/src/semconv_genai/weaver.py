"""Weaver binary management: version pinning, download, and caching."""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from semconv_genai.versions import require_pin

logger = logging.getLogger(__name__)

WEAVER_VERSION = require_pin("WEAVER_VERSION")


def _normalize_version(version: str) -> str:
    """Normalize optional leading-v version strings for comparisons."""
    return version[1:] if version.startswith("v") else version


def path_from_env(var_name: str, default_path: Path) -> Path:
    value = os.environ.get(var_name)
    if value:
        return Path(value)
    return default_path


def _weaver_binary_name() -> str:
    """Return the platform-specific Weaver binary name."""
    return "weaver.exe" if sys.platform == "win32" else "weaver"


def _weaver_asset_name() -> str:
    """Return the pinned Weaver release asset name for the current platform."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in {"amd64", "x86_64"}:
        return "weaver-x86_64-pc-windows-msvc.zip"
    if sys.platform == "linux" and machine in {"amd64", "x86_64"}:
        return "weaver-x86_64-unknown-linux-gnu.tar.xz"
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return "weaver-aarch64-apple-darwin.tar.xz"
    if sys.platform == "darwin" and machine in {"amd64", "x86_64"}:
        return "weaver-x86_64-apple-darwin.tar.xz"
    raise RuntimeError(f"Unsupported platform for managed Weaver install: {sys.platform} / {platform.machine()}")


def _find_weaver_binary(search_root: Path) -> Path | None:
    """Return the first Weaver binary found under the given directory."""
    for path in search_root.rglob(_weaver_binary_name()):
        if path.is_file():
            return path
    return None


def _weaver_version(binary: str | Path) -> str:
    """Return the normalized version reported by a Weaver binary, or an empty string."""
    try:
        proc = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""

    output = f"{proc.stdout}\n{proc.stderr}"
    match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", output)
    return match.group(1) if match else ""


def _download_file(url: str, destination: Path) -> None:
    """Download a file over HTTPS from github.com to disk."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise RuntimeError(f"Refusing to download non-github.com URL: {url}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def ensure_weaver() -> Path:
    """Ensure the pinned Weaver version is available and return its binary path."""
    expected_version = _normalize_version(WEAVER_VERSION)

    system_weaver = shutil.which(_weaver_binary_name())
    if system_weaver and _weaver_version(system_weaver) == expected_version:
        return Path(system_weaver)

    cache_root = path_from_env(
        "WEAVER_CACHE",
        Path.home() / ".cache" / "semconv-genai" / "weaver",
    )
    install_dir = cache_root / WEAVER_VERSION.replace("/", "_")
    cached_binary = _find_weaver_binary(install_dir) if install_dir.exists() else None
    if cached_binary and _weaver_version(cached_binary) == expected_version:
        return cached_binary

    asset_name = _weaver_asset_name()
    download_url = f"https://github.com/open-telemetry/weaver/releases/download/{WEAVER_VERSION}/{asset_name}"
    install_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        dir=str(install_dir.parent),
        prefix=f"weaver-{expected_version}-",
    ) as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / asset_name
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        logger.info("Downloading Weaver %s", WEAVER_VERSION)
        _download_file(download_url, archive_path)

        if archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_dir)
        else:
            with tarfile.open(archive_path, "r:*") as archive:
                archive.extractall(extract_dir)

        extracted_binary = _find_weaver_binary(extract_dir)
        if extracted_binary is None:
            raise RuntimeError(f"Downloaded Weaver archive did not contain {_weaver_binary_name()}")

        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.copytree(extract_dir, install_dir)

    cached_binary = _find_weaver_binary(install_dir)
    if cached_binary is None:
        raise RuntimeError(f"Installed Weaver binary not found under {install_dir}")
    if sys.platform != "win32":
        cached_binary.chmod(cached_binary.stat().st_mode | 0o111)
    installed_version = _weaver_version(cached_binary)
    if installed_version != expected_version:
        raise RuntimeError(
            f"Installed Weaver version mismatch: expected {WEAVER_VERSION}, found {installed_version or 'unknown'}"
        )
    return cached_binary
