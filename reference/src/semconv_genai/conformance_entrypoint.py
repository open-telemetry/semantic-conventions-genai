"""Run GenAI conformance with a longer Weaver startup window."""

from __future__ import annotations

import os
import sys

from opentelemetry.test import weaver_live_check

_DEFAULT_STARTUP_RETRIES = 60
_STARTUP_RETRIES_ENV = "OTEL_CONFORMANCE_WEAVER_STARTUP_RETRIES"
_original_retry = weaver_live_check.Retry


def _extended_startup_retry(*args: object, **kwargs: object) -> object:
    if kwargs.get("total") == 10:
        kwargs["total"] = int(os.getenv(_STARTUP_RETRIES_ENV, str(_DEFAULT_STARTUP_RETRIES)))
    return _original_retry(*args, **kwargs)


def main() -> int:
    # The upstream startup wait is fixed at about 10 seconds. Large registries
    # can take longer to resolve on cold CI runners.
    weaver_live_check.Retry = _extended_startup_retry

    from genai_conformance import cli

    return cli()


if __name__ == "__main__":
    sys.exit(main())
