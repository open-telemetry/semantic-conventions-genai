"""System-instruction model and schema regressions.

Run from this directory:
    uv run --frozen --with jsonschema==4.26.0 python -m unittest -v test_system_instructions
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft7Validator, Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import TypeAdapter, ValidationError

from models import GenericPart, SystemInstructionPart, SystemInstructions, TextPart

MODEL_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = MODEL_DIR.parents[2] / "model/gen-ai/gen-ai-system-instructions.json"


class SystemInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.validators = []
        for validator_type in (Draft7Validator, Draft202012Validator):
            validator_type.check_schema(self.schema)
            self.validators.append(validator_type(self.schema))

    def assert_round_trip(self, parts):
        instructions = SystemInstructions.model_validate(parts)
        self.assertEqual(instructions.model_dump(), parts)
        serialized = instructions.model_dump_json()
        self.assertEqual(json.loads(serialized), parts)
        restored = SystemInstructions.model_validate_json(serialized)
        self.assertEqual(restored.model_dump(), parts)
        for validator in self.validators:
            with self.subTest(validator=type(validator).__name__):
                validator.validate(json.loads(serialized))
        return instructions

    def assert_rejected(self, parts):
        with (
            self.subTest(validator="Pydantic Python"),
            self.assertRaises(ValidationError),
        ):
            SystemInstructions.model_validate(parts)
        with (
            self.subTest(validator="Pydantic JSON"),
            self.assertRaises(ValidationError),
        ):
            SystemInstructions.model_validate_json(json.dumps(parts))
        for validator in self.validators:
            with (
                self.subTest(validator=type(validator).__name__),
                self.assertRaises(SchemaValidationError),
            ):
                validator.validate(parts)

    def python_entry_points(self, part):
        return (
            (
                "model_validate",
                lambda: SystemInstructions.model_validate([part]).root[0],
            ),
            ("constructor", lambda: SystemInstructions(root=[part]).root[0]),
            (
                "type_adapter",
                lambda: TypeAdapter(SystemInstructionPart).validate_python(part),
            ),
        )

    def assert_vendor_instance_round_trip(self, part):
        expected = {"type": "vendor_note", "value": 7}
        self.assertIsInstance(part, GenericPart)
        self.assertEqual(part.model_dump(), expected)
        self.assertEqual(json.loads(part.model_dump_json()), expected)

    def test_model_validate_accepts_existing_generic_part(self):
        part = GenericPart(type="vendor_note", value=7)
        instructions = SystemInstructions.model_validate([part])
        self.assert_vendor_instance_round_trip(instructions.root[0])

    def test_constructor_accepts_existing_generic_part(self):
        part = GenericPart(type="vendor_note", value=7)
        instructions = SystemInstructions(root=[part])
        self.assert_vendor_instance_round_trip(instructions.root[0])

    def test_type_adapter_accepts_existing_generic_part(self):
        part = GenericPart(type="vendor_note", value=7)
        validated = TypeAdapter(SystemInstructionPart).validate_python(part)
        self.assert_vendor_instance_round_trip(validated)

    def test_generic_instances_preserve_raw_python_extra_values(self):
        part = GenericPart(
            type="vendor_note",
            value=7,
            marker=object(),
            nested=GenericPart(type="vendor_detail", value=None),
            payload=bytearray(b"\x00\xff"),
            mapping={1: [object()]},
        )
        extras = part.model_extra
        original_values = dict(extras)
        for entry_point, validate in self.python_entry_points(part):
            with self.subTest(entry_point=entry_point):
                validated = validate()
                self.assertIsInstance(validated, GenericPart)
                self.assertEqual(validated.type, part.type)
                self.assertEqual(validated.model_fields_set, part.model_fields_set)
                self.assertEqual(validated.model_extra, original_values)
                self.assertIs(part.model_extra, extras)
                for name, value in original_values.items():
                    self.assertIs(validated.model_extra[name], value)
                    self.assertIs(part.model_extra[name], value)

    def test_generic_text_instances_still_require_valid_text(self):
        for fields in (
            {},
            {"content": 123},
            {"content": None},
            {"content": False},
            {"content": []},
            {"content": {}},
        ):
            part = GenericPart(type="text", **fields)
            for entry_point, validate in self.python_entry_points(part):
                with (
                    self.subTest(entry_point=entry_point, fields=fields),
                    self.assertRaises(ValidationError),
                ):
                    validate()

    def test_valid_generic_text_instances_use_text_part(self):
        marker = object()
        part = GenericPart(type="text", content="hello", vendor_option=marker)
        for entry_point, validate in self.python_entry_points(part):
            with self.subTest(entry_point=entry_point):
                validated = validate()
                self.assertIsInstance(validated, TextPart)
                self.assertEqual(validated.content, "hello")
                self.assertIs(validated.model_extra["vendor_option"], marker)

    def test_valid_text_round_trips_as_text_part(self):
        for content in ("hello", ""):
            with self.subTest(content=content):
                instructions = self.assert_round_trip(
                    [{"type": "text", "content": content}]
                )
                self.assertIsInstance(instructions.root[0], TextPart)

    def test_text_requires_content(self):
        self.assert_rejected([{"type": "text"}])

    def test_text_requires_string_content(self):
        for content in (123, 1.5, True, None, [], {}):
            with self.subTest(content=content):
                self.assert_rejected([{"type": "text", "content": content}])

    def test_unknown_tags_round_trip_with_extra_fields(self):
        for tag in ("vendor_note", "custom", "tool_call"):
            with self.subTest(tag=tag):
                instructions = self.assert_round_trip(
                    [
                        {
                            "type": tag,
                            "content": {"values": [1, None, True]},
                            "vendor_option": "keep",
                        }
                    ]
                )
                self.assertIsInstance(instructions.root[0], GenericPart)
                restored = SystemInstructions.model_validate(instructions.root)
                self.assertEqual(restored.model_dump(), instructions.model_dump())

    def test_text_preserves_extra_fields(self):
        instructions = self.assert_round_trip(
            [{"type": "text", "content": "hello", "vendor_option": {"keep": True}}]
        )
        self.assertIsInstance(instructions.root[0], TextPart)

    def test_mixed_parts_preserve_order(self):
        instructions = self.assert_round_trip(
            [
                {"type": "vendor_note", "value": 7},
                {"type": "text", "content": "hello"},
                {"type": "vendor_note"},
            ]
        )
        self.assertIsInstance(instructions.root[1], TextPart)

    def test_empty_instructions_round_trip(self):
        self.assert_round_trip([])

    def test_type_is_still_required_and_must_be_a_string(self):
        for part in ({}, {"type": None}, {"type": 123}):
            with self.subTest(part=part):
                self.assert_rejected([part])

    def test_schema_matches_validation_and_serialization_modes(self):
        for mode in ("validation", "serialization"):
            with self.subTest(mode=mode):
                self.assertEqual(
                    SystemInstructions.model_json_schema(mode=mode), self.schema
                )

    def test_generator_reproduces_committed_system_schema(self):
        with tempfile.TemporaryDirectory() as output_dir:
            subprocess.run(
                [sys.executable, str(MODEL_DIR / "models.py"), output_dir],
                check=True,
                capture_output=True,
                text=True,
            )
            generated = Path(output_dir) / SCHEMA_PATH.name
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                SCHEMA_PATH.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
