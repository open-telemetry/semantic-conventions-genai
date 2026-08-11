"""External version pins, read from the repository-root ``versions.env``."""

from __future__ import annotations

from semconv_genai import SEMCONV_ROOT

VERSIONS_FILE = SEMCONV_ROOT / "versions.env"


def _load_version_pins() -> dict[str, str]:
    try:
        content = VERSIONS_FILE.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"Could not read version pins file: {VERSIONS_FILE}") from e

    pins: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise RuntimeError(f"Invalid version pin line in {VERSIONS_FILE}: {raw_line!r}")
        pins[key.strip()] = value.strip().strip('"').strip("'")
    return pins


def require_pin(name: str) -> str:
    pins = _load_version_pins()
    try:
        return pins[name]
    except KeyError:
        raise RuntimeError(f"{VERSIONS_FILE} is missing the pin {name}") from None
