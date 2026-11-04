"""Tests for the JSON form of ``BlobPart.content`` in ``models.py``.

JSON Schema treats ``contentEncoding`` as an annotation, so the schema snapshot
cases can't check the encoding; these tests run the models instead.
"""

import json

import pytest
from pydantic import ValidationError

from models import BlobPart, InputMessages, OutputMessages

# Raw bytes and their standard base64 form. b"\xfb\xff" encodes to `+` and `/`,
# which the URL-safe alphabet replaces with `-` and `_`.
SAMPLES = [
    pytest.param(b"", "", id="empty"),
    pytest.param(b"hello", "aGVsbG8=", id="ascii"),
    pytest.param(b"\xfb\xff", "+/8=", id="plus-and-slash"),
]

INVALID_BASE64 = [
    pytest.param("not base64!", id="not-base64"),
    pytest.param("-_8=", id="url-safe-alphabet"),
    pytest.param("aGVsbG8", id="missing-padding"),
]


def blob_part(content: bytes | str) -> dict:
    return {"type": "blob", "modality": "image", "mime_type": "image/png", "content": content}


@pytest.mark.parametrize(("raw", "encoded"), SAMPLES)
def test_json_uses_standard_base64(raw: bytes, encoded: str):
    part = BlobPart(**blob_part(raw))
    assert json.loads(part.model_dump_json())["content"] == encoded
    assert BlobPart.model_validate_json(json.dumps(blob_part(encoded))).content == raw


@pytest.mark.parametrize("content", INVALID_BASE64)
def test_json_rejects_invalid_base64(content: str):
    with pytest.raises(ValidationError) as raised:
        BlobPart.model_validate_json(json.dumps(blob_part(content)))
    assert raised.value.errors()[0]["loc"] == ("content",)


def test_python_mode_keeps_raw_bytes():
    part = BlobPart(**blob_part(b"+/8="))
    assert part.content == b"+/8="
    assert part.model_dump()["content"] == b"+/8="


@pytest.mark.parametrize(("model", "role"), [(InputMessages, "user"), (OutputMessages, "assistant")])
def test_messages_round_trip_blob_bytes(model: type[InputMessages | OutputMessages], role: str):
    messages = model.model_validate([{"role": role, "parts": [blob_part(b"\xfb\xff")]}])
    wire = messages.model_dump_json()
    assert json.loads(wire)[0]["parts"][0]["content"] == "+/8="
    assert model.model_validate_json(wire) == messages
