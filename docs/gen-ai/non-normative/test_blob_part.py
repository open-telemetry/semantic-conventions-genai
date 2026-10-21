"""BlobPart wire-format regressions.

Run from the repository root with ``make test-json-schemas``.
"""

import json
import unittest
from collections import UserDict
from enum import Enum
from pathlib import Path

from jsonschema import Draft7Validator, Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from models import (
    SCHEMAS,
    BlobPart,
    ChatMessage,
    CompactionPart,
    FilePart,
    GenericPart,
    InputMessages,
    MessagePart,
    OutputMessage,
    OutputMessages,
    ReasoningPart,
    ServerToolCallPart,
    ServerToolCallResponsePart,
    SystemInstructions,
    TextPart,
    ToolCallRequestPart,
    ToolCallResponsePart,
    UriPart,
)


class PythonPartTag(Enum):
    BLOB = "blob"
    VENDOR_NOTE = "vendor_note"
    TEXT = "text"
    CAPITALIZED_BLOB = "Blob"
    PADDED_BLOB = "blob "


class BlobPartTests(unittest.TestCase):
    samples = (
        (b"hello", "aGVsbG8="),
        (b"\x89PNG\r\n\x1a\n", "iVBORw0KGgo="),
        (b"", ""),
        (b"\xfb\xff", "+/8="),
        (b"aGVsbG8=", "YUdWc2JHOD0="),
    )
    python_validation_modes = (
        ("default", {}),
        ("lax", {"strict": False}),
        ("strict", {"strict": True}),
    )

    def payload(self, content):
        return {
            "type": "blob",
            "modality": "image",
            "mime_type": "application/octet-stream",
            "content": content,
        }

    def message_values(self, part):
        input_message = {"role": "user", "parts": [part]}
        output_message = {"role": "assistant", "parts": [part]}
        return (
            ("MessagePart", TypeAdapter(MessagePart), part),
            ("ChatMessage", TypeAdapter(ChatMessage), input_message),
            ("OutputMessage", TypeAdapter(OutputMessage), output_message),
            ("InputMessages", TypeAdapter(InputMessages), [input_message]),
            ("OutputMessages", TypeAdapter(OutputMessages), [output_message]),
        )

    def first_part(self, value):
        if isinstance(value, (InputMessages, OutputMessages)):
            return value.root[0].parts[0]
        if isinstance(value, ChatMessage):
            return value.parts[0]
        return value

    def invalid_blob_shapes(self):
        missing_content = self.payload("")
        del missing_content["content"]
        missing_modality = self.payload("")
        del missing_modality["modality"]
        return (
            missing_content,
            missing_modality,
            self.payload(None),
            self.payload(123),
            self.payload([]),
            self.payload({}),
        )

    def test_python_entry_points_preserve_raw_bytes(self):
        adapter = TypeAdapter(BlobPart)
        for raw, _ in self.samples:
            with self.subTest(raw=raw):
                payload = self.payload(raw)
                parts = (
                    BlobPart(**payload),
                    BlobPart.model_validate(payload, strict=True),
                    adapter.validate_python(payload),
                )
                for part in parts:
                    self.assertEqual(part.content, raw)
                    self.assertEqual(part.model_dump()["content"], raw)
                    self.assertEqual(
                        BlobPart.model_validate(part.model_dump()).content, raw
                    )

    def test_python_strings_keep_their_utf8_behavior(self):
        for content in ("hello", "aGVsbG8=", "+/8=", "café"):
            with self.subTest(content=content):
                payload = self.payload(content)
                self.assertEqual(BlobPart(**payload).content, content.encode("utf-8"))
                self.assertEqual(
                    BlobPart.model_validate(payload).content, content.encode("utf-8")
                )

    def test_json_serialization_uses_standard_base64(self):
        adapter = TypeAdapter(BlobPart)
        for raw, encoded in self.samples:
            with self.subTest(raw=raw):
                part = BlobPart(**self.payload(raw))
                expected = self.payload(encoded)
                self.assertEqual(json.loads(part.model_dump_json()), expected)
                self.assertEqual(part.model_dump(mode="json"), expected)
                self.assertEqual(json.loads(adapter.dump_json(part)), expected)

    def test_json_entry_points_decode_standard_base64(self):
        adapter = TypeAdapter(BlobPart)
        for raw, encoded in self.samples:
            with self.subTest(raw=raw):
                wire = json.dumps(self.payload(encoded))
                self.assertEqual(BlobPart.model_validate_json(wire).content, raw)
                self.assertEqual(
                    BlobPart.model_validate_json(wire, strict=True).content, raw
                )
                self.assertEqual(adapter.validate_json(wire.encode()).content, raw)

    def test_json_round_trips_preserve_bytes(self):
        for raw, _ in self.samples:
            with self.subTest(raw=raw):
                part = BlobPart(**self.payload(raw))
                restored = BlobPart.model_validate_json(part.model_dump_json())
                self.assertEqual(restored, part)
                self.assertEqual(restored.content, raw)

    def test_input_and_output_message_round_trips(self):
        for model, role in ((InputMessages, "user"), (OutputMessages, "assistant")):
            for raw, encoded in self.samples:
                with self.subTest(model=model.__name__, raw=raw):
                    messages = model.model_validate(
                        [{"role": role, "parts": [self.payload(raw)]}]
                    )
                    self.assertIsInstance(messages.root[0].parts[0], BlobPart)
                    self.assertEqual(
                        json.loads(messages.model_dump_json())[0]["parts"][0],
                        self.payload(encoded),
                    )
                    wire = json.dumps(
                        [{"role": role, "parts": [self.payload(encoded)]}]
                    )
                    restored = model.model_validate_json(wire)
                    self.assertIsInstance(restored.root[0].parts[0], BlobPart)
                    self.assertEqual(restored.root[0].parts[0].content, raw)
                    self.assertEqual(restored, messages)

    def test_missing_null_and_empty_content_are_distinct(self):
        missing = self.payload(None)
        del missing["content"]
        for payload, error_type in (
            (missing, "missing"),
            (self.payload(None), "bytes_type"),
        ):
            for json_mode in (False, True):
                with self.subTest(payload=payload, json_mode=json_mode):
                    with self.assertRaises(ValidationError) as raised:
                        if json_mode:
                            BlobPart.model_validate_json(json.dumps(payload))
                        else:
                            BlobPart.model_validate(payload)
                    self.assertEqual(raised.exception.errors()[0]["loc"], ("content",))
                    self.assertEqual(raised.exception.errors()[0]["type"], error_type)

        part = BlobPart.model_validate_json(json.dumps(self.payload("")))
        self.assertEqual(part.content, b"")
        self.assertEqual(
            part.model_dump(
                mode="json",
                exclude_none=True,
                exclude_defaults=True,
                exclude_unset=True,
            )["content"],
            "",
        )

    def test_json_rejects_invalid_base64(self):
        for content in ("not base64!", "-_8=", "aGVsbG8", "aGVs\nbG8=", "é"):
            with self.subTest(content=content):
                with self.assertRaises(ValidationError) as raised:
                    BlobPart.model_validate_json(json.dumps(self.payload(content)))
                self.assertEqual(raised.exception.errors()[0]["loc"], ("content",))

    def test_message_entry_points_reject_invalid_json_blobs(self):
        malformed = [
            self.payload(content)
            for content in ("not base64!", "-_8=", "aGVsbG8", "aGVs\nbG8=", "é")
        ]
        for payload in (*malformed, *self.invalid_blob_shapes()):
            for name, adapter, value in self.message_values(payload):
                for strict in (False, True):
                    with self.subTest(surface=name, payload=payload, strict=strict):
                        with self.assertRaises(ValidationError) as raised:
                            adapter.validate_json(json.dumps(value), strict=strict)
                        self.assertTrue(
                            any(
                                error["loc"][-1] in ("content", "modality")
                                for error in raised.exception.errors()
                            )
                        )

    def test_message_entry_points_reject_invalid_python_blob_shapes(self):
        for payload in self.invalid_blob_shapes():
            for name, adapter, value in self.message_values(payload):
                with (
                    self.subTest(surface=name, payload=payload),
                    self.assertRaises(ValidationError),
                ):
                    adapter.validate_python(value)

    def test_generic_blob_instances_cannot_bypass_validation(self):
        for content in (b"\xfb\xff", "not base64!", None):
            generic_blob = GenericPart(**self.payload(content))
            for name, adapter, value in self.message_values(generic_blob):
                with (
                    self.subTest(surface=name, content=content),
                    self.assertRaises(ValidationError),
                ):
                    adapter.validate_python(value)

    def test_message_entry_points_reject_coerced_blob_tags(self):
        for tag in (b"blob", bytearray(b"blob"), PythonPartTag.BLOB):
            for content in (None, b"hello"):
                payload = {**self.payload(content), "type": tag}
                for name, adapter, value in self.message_values(payload):
                    for mode, options in self.python_validation_modes:
                        with self.subTest(
                            surface=name, tag=tag, content=content, mode=mode
                        ):
                            with self.assertRaises(ValidationError) as raised:
                                adapter.validate_python(value, **options)
                            if mode != "strict":
                                error = raised.exception.errors()[0]
                                self.assertEqual(error["type"], "value_error")
                                self.assertIn("BlobPart", error["msg"])

    def test_non_blob_tag_coercion_preserves_round_trips(self):
        for enum_tag in (
            PythonPartTag.VENDOR_NOTE,
            PythonPartTag.TEXT,
            PythonPartTag.CAPITALIZED_BLOB,
            PythonPartTag.PADDED_BLOB,
        ):
            for tag in (
                enum_tag.value.encode(),
                bytearray(enum_tag.value.encode()),
                enum_tag,
            ):
                payload = {**self.payload("plain text"), "type": tag}
                for name, adapter, value in self.message_values(payload):
                    for mode, options in self.python_validation_modes:
                        with self.subTest(surface=name, tag=tag, mode=mode):
                            if mode == "strict":
                                with self.assertRaises(ValidationError):
                                    adapter.validate_python(value, **options)
                                continue
                            parsed = adapter.validate_python(value, **options)
                            self.assertEqual(
                                self.first_part(parsed).type, enum_tag.value
                            )
                            wire = adapter.dump_json(parsed, warnings="error")
                            for validator_type in (
                                Draft7Validator,
                                Draft202012Validator,
                            ):
                                validator_type(adapter.json_schema()).validate(
                                    json.loads(wire)
                                )
                            restored = adapter.validate_json(wire, strict=True)
                            self.assertEqual(
                                adapter.dump_python(restored, mode="json"),
                                json.loads(wire),
                            )

    def test_string_blob_tags_round_trip_in_all_python_modes(self):
        for raw, encoded in self.samples:
            for part in (self.payload(raw), BlobPart(**self.payload(raw))):
                for name, adapter, value in self.message_values(part):
                    for mode, options in self.python_validation_modes:
                        with self.subTest(
                            surface=name,
                            raw=raw,
                            part_class=type(part).__name__,
                            mode=mode,
                        ):
                            parsed = adapter.validate_python(value, **options)
                            self.assertIsInstance(self.first_part(parsed), BlobPart)
                            wire = adapter.dump_json(parsed, warnings="error")
                            Draft202012Validator(adapter.json_schema()).validate(
                                json.loads(wire)
                            )
                            restored = self.first_part(
                                adapter.validate_json(wire, strict=True)
                            )
                            self.assertEqual(restored.content, raw)
                            self.assertEqual(
                                restored.model_dump(mode="json"), self.payload(encoded)
                            )

    def test_generic_and_system_blob_tag_coercion_is_unchanged(self):
        for tag in (b"blob", bytearray(b"blob"), PythonPartTag.BLOB):
            with self.subTest(tag=tag):
                payload = {**self.payload(None), "type": tag}
                part = GenericPart(**payload)
                self.assertEqual(part.type, "blob")
                self.assertIs(SystemInstructions([part]).root[0], part)
                parsed = SystemInstructions.model_validate([payload])
                self.assertEqual(parsed.root[0].model_dump(), part.model_dump())
                restored = SystemInstructions.model_validate_json(
                    parsed.model_dump_json(warnings="error")
                )
                self.assertEqual(restored.root[0].model_dump(), part.model_dump())

    def test_message_entry_points_round_trip_blob_bytes(self):
        for raw, encoded in self.samples:
            for name, adapter, value in self.message_values(self.payload(raw)):
                with self.subTest(surface=name, raw=raw):
                    original = adapter.validate_python(value, strict=True)
                    part = self.first_part(original)
                    self.assertIsInstance(part, BlobPart)
                    self.assertEqual(part.content, raw)
                    self.assertEqual(
                        part.model_dump(mode="json"), self.payload(encoded)
                    )
                    wire = adapter.dump_json(original, warnings="error")
                    restored = adapter.validate_json(wire, strict=True)
                    self.assertIsInstance(self.first_part(restored), BlobPart)
                    self.assertEqual(self.first_part(restored).content, raw)
                    self.assertEqual(
                        adapter.dump_python(restored), adapter.dump_python(original)
                    )
                    self.assertEqual(
                        adapter.dump_python(restored, mode="json"), json.loads(wire)
                    )

    def test_message_python_strings_remain_raw_utf8(self):
        for content in ("not base64!", "+/8=", "aGVsbG8=", "café"):
            for name, adapter, value in self.message_values(self.payload(content)):
                with self.subTest(surface=name, content=content):
                    parsed = adapter.validate_python(value)
                    self.assertIsInstance(self.first_part(parsed), BlobPart)
                    self.assertEqual(
                        self.first_part(parsed).content, content.encode("utf-8")
                    )

    def test_mapping_inputs_follow_the_same_blob_routing(self):
        for raw, _ in self.samples:
            payload = UserDict(self.payload(raw))
            for name, adapter, value in self.message_values(payload):
                with self.subTest(surface=name, raw=raw):
                    parsed = adapter.validate_python(value)
                    self.assertIsInstance(self.first_part(parsed), BlobPart)
                    self.assertEqual(self.first_part(parsed).content, raw)
        for payload in self.invalid_blob_shapes():
            for name, adapter, value in self.message_values(UserDict(payload)):
                with (
                    self.subTest(surface=name, payload=payload),
                    self.assertRaises(ValidationError),
                ):
                    adapter.validate_python(value)

    def test_unknown_generic_instances_preserve_identity_and_extra_fields(self):
        class VendorPart(GenericPart):
            detail: str

        for tag in ("vendor_note", "vendor.blob", "Blob", " blob", "blob ", ""):
            for part in (
                GenericPart(type=tag, content="+/8=", custom={"nested": [None, 1]}),
                VendorPart(type=tag, detail="provider", content=None),
            ):
                for name, adapter, value in self.message_values(part):
                    with self.subTest(
                        surface=name, tag=tag, part_class=type(part).__name__
                    ):
                        parsed = adapter.validate_python(value, strict=True)
                        self.assertIs(self.first_part(parsed), part)
                        wire = adapter.dump_json(parsed, warnings="error")
                        restored = adapter.validate_json(wire)
                        self.assertIsInstance(self.first_part(restored), GenericPart)
                        self.assertEqual(
                            self.first_part(restored).model_dump(),
                            TypeAdapter(GenericPart).dump_python(part, mode="json"),
                        )

    def test_other_message_variants_keep_existing_behavior(self):
        cases = (
            (TextPart, {"type": "text", "content": "+/8="}),
            (
                ToolCallRequestPart,
                {"type": "tool_call", "name": "tool", "arguments": {}},
            ),
            (ToolCallResponsePart, {"type": "tool_call_response", "response": None}),
            (
                ServerToolCallPart,
                {
                    "type": "server_tool_call",
                    "name": "tool",
                    "server_tool_call": {"type": "vendor_tool"},
                },
            ),
            (
                ServerToolCallResponsePart,
                {
                    "type": "server_tool_call_response",
                    "server_tool_call_response": {"type": "vendor_result"},
                },
            ),
            (FilePart, {"type": "file", "modality": "image", "file_id": "file-1"}),
            (
                UriPart,
                {
                    "type": "uri",
                    "modality": "image",
                    "uri": "https://example.com/a.png",
                },
            ),
            (ReasoningPart, {"type": "reasoning", "content": "reason"}),
            (CompactionPart, {"type": "compaction"}),
            (GenericPart, {"type": "text", "content": 123}),
            (GenericPart, {"type": "tool_call"}),
            (GenericPart, {"type": "vendor_note", "content": "not base64!"}),
        )
        for expected_type, payload in cases:
            for name, adapter, value in self.message_values(payload):
                with self.subTest(surface=name, payload=payload):
                    parsed = adapter.validate_json(json.dumps(value))
                    part = self.first_part(parsed)
                    self.assertIsInstance(part, expected_type)
                    self.assertEqual(
                        part.model_dump(mode="json", exclude_unset=True), payload
                    )
                    self.assertEqual(
                        adapter.validate_json(
                            adapter.dump_json(parsed, warnings="error")
                        ),
                        parsed,
                    )

    def test_system_instruction_blob_tags_are_not_changed(self):
        payload = self.payload("not base64!")
        part = GenericPart(**payload)
        self.assertIs(SystemInstructions([part]).root[0], part)
        restored = SystemInstructions.model_validate_json(json.dumps([payload]))
        self.assertIsInstance(restored.root[0], GenericPart)
        self.assertEqual(json.loads(restored.model_dump_json()), [payload])

    def test_non_blob_parts_keep_their_content(self):
        parts = [
            {"type": "text", "content": "+/8="},
            {"type": "vendor_note", "content": "+/8=", "custom": 1},
            {"type": "vendor_note", "content": ""},
            {"type": "vendor_note", "content": None},
            {"type": "vendor_note"},
        ]
        for model, role in ((InputMessages, "user"), (OutputMessages, "assistant")):
            with self.subTest(model=model.__name__):
                messages = model.model_validate_json(
                    json.dumps([{"role": role, "parts": parts}])
                )
                self.assertIsInstance(messages.root[0].parts[0], TextPart)
                for part in messages.root[0].parts[1:]:
                    self.assertIsInstance(part, GenericPart)
                self.assertEqual(
                    json.loads(messages.model_dump_json())[0]["parts"], parts
                )

    def test_blob_schema_describes_standard_base64_in_both_modes(self):
        for mode in ("validation", "serialization"):
            with self.subTest(mode=mode):
                schema = BlobPart.model_json_schema(mode=mode)
                schema.pop("$defs")
                content = schema["properties"]["content"]
                self.assertEqual(content["type"], "string")
                self.assertEqual(content.get("contentEncoding"), "base64")
                self.assertNotIn("format", content)
                self.assertNotIn("default", content)
                self.assertIn("content", schema["required"])
                for model in (InputMessages, OutputMessages):
                    self.assertEqual(
                        model.model_json_schema(mode=mode)["$defs"]["BlobPart"], schema
                    )

    def test_committed_schemas_match_generator(self):
        schema_dir = Path(__file__).resolve().parents[3] / "model" / "gen-ai"
        for filename, model in SCHEMAS.items():
            with self.subTest(filename=filename):
                expected = json.dumps(model.model_json_schema(), indent=4) + "\n"
                self.assertEqual(
                    (schema_dir / filename).read_text(encoding="utf-8"), expected
                )

    def test_committed_message_schemas_validate_blob_shapes(self):
        schema_dir = Path(__file__).resolve().parents[3] / "model" / "gen-ai"
        for filename in ("gen-ai-input-messages.json", "gen-ai-output-messages.json"):
            schema = json.loads((schema_dir / filename).read_text(encoding="utf-8"))
            for validator_type in (Draft7Validator, Draft202012Validator):
                with self.subTest(schema=filename, draft=validator_type.__name__):
                    validator_type.check_schema(schema)
                    validator = validator_type(schema)
                    for raw, _ in self.samples:
                        part = BlobPart(**self.payload(raw)).model_dump(mode="json")
                        validator.validate([{"role": "user", "parts": [part]}])
                    for part in self.invalid_blob_shapes():
                        self.assertFalse(
                            validator.is_valid([{"role": "user", "parts": [part]}]),
                            part,
                        )
                    for part in (
                        {"type": "text", "content": "+/8="},
                        {"type": "text", "content": 123},
                        {"type": "vendor_note"},
                        {"type": "vendor_note", "content": None},
                        {"type": "vendor_note", "content": ""},
                        {"type": "vendor_note", "content": "not base64!"},
                    ):
                        validator.validate([{"role": "user", "parts": [part]}])

    def test_content_encoding_is_an_annotation_not_base64_validation(self):
        for model in (InputMessages, OutputMessages):
            payload = [{"role": "user", "parts": [self.payload("not base64!")]}]
            with self.subTest(model=model.__name__):
                Draft202012Validator(model.model_json_schema()).validate(payload)
                with self.assertRaises(ValidationError):
                    model.model_validate_json(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
