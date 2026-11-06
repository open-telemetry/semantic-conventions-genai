"""Regression checks for transient Weaver download failures."""

import io
import urllib.error
from unittest.mock import patch

import pytest

from semconv_genai.weaver import _download_file

URL = "https://github.com/open-telemetry/weaver/releases/download/v0.28.0/weaver.tar.xz"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_download_retries_transient_http_errors(tmp_path, status):
    error = urllib.error.HTTPError(URL, status, "temporary failure", None, None)
    destination = tmp_path / "weaver.tar.xz"
    with (
        patch("semconv_genai.weaver.urllib.request.urlopen", side_effect=[error, io.BytesIO(b"archive")]) as open_url,
        patch("time.sleep"),
    ):
        _download_file(URL, destination)
    assert open_url.call_count == 2
    assert destination.read_bytes() == b"archive"


def test_download_stops_after_repeated_gateway_timeouts(tmp_path):
    error = urllib.error.HTTPError(URL, 504, "Gateway Time-out", None, None)
    with (
        patch("semconv_genai.weaver.urllib.request.urlopen", side_effect=error) as open_url,
        patch("time.sleep") as sleep,
        pytest.raises(urllib.error.HTTPError) as caught,
    ):
        _download_file(URL, tmp_path / "weaver.tar.xz")
    assert caught.value is error
    assert open_url.call_count == 3
    assert sleep.call_count == 2


def test_download_does_not_retry_missing_assets(tmp_path):
    error = urllib.error.HTTPError(URL, 404, "Not Found", None, None)
    with (
        patch("semconv_genai.weaver.urllib.request.urlopen", side_effect=error) as open_url,
        patch("time.sleep") as sleep,
        pytest.raises(urllib.error.HTTPError) as caught,
    ):
        _download_file(URL, tmp_path / "weaver.tar.xz")
    assert caught.value is error
    assert open_url.call_count == 1
    sleep.assert_not_called()
