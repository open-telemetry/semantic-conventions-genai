"""Snapshot tests for the committed JSON schemas under model/gen-ai/.

Each ``tests/cases/<case>.yaml`` names a schema and holds a sample document
plus the errors that schema reports for it (``errors: []`` means the document
is valid). The errors are a snapshot: write a case with ``description``,
``schema`` and ``document``, run ``uv run pytest --update-snapshots`` to fill
in ``errors``, and review the result. A later schema change that alters the
errors fails the plain ``uv run pytest`` run with a diff.
"""

import io
import json
import re
from pathlib import Path
from typing import TypedDict

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from ruamel.yaml import YAML

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
CASE_SCHEMA_FILE = HERE / "case.schema.json"
SCHEMA_DIR = HERE.parents[3] / "model" / "gen-ai"

SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.json"))
CASE_FILES = sorted(CASES_DIR.glob("*.yaml"))

ERRORS_KEY = "errors"
ERRORS_COMMENT = "# Regenerate with `uv run pytest --update-snapshots`, do not edit by hand.\n"

load_yaml = YAML(typ="safe", pure=True)
dump_yaml = YAML()
dump_yaml.indent(mapping=2, sequence=4, offset=2)
dump_yaml.width = 4096


class Error(TypedDict):
    """One snapshotted validation error, a subset of ``jsonschema.ValidationError``."""

    path: str
    keyword: str
    message: str


def load_validator(schema_file: Path) -> Draft202012Validator:
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


VALIDATORS = {f.name: load_validator(f) for f in SCHEMA_FILES}


def sort_key(error: ValidationError) -> tuple[str, str, str]:
    return (error.json_path, str(error.validator), error.message)


def unwrap(error: ValidationError) -> list[ValidationError]:
    """Unwrap anyOf/oneOf errors when a single branch applies or all branches fail the same way."""
    if not error.context:
        return [error]
    branches: dict[int, list[ValidationError]] = {}
    for sub in error.context:
        branches.setdefault(int(sub.schema_path[0]), []).append(sub)
    non_null = [
        b
        for b in branches.values()
        if not (len(b) == 1 and b[0].validator == "type" and b[0].validator_value == "null")
    ]
    # If a single branch matched the `type` discriminator, report all of its errors.
    type_matched = [
        b
        for b in non_null
        if not any(
            list(e.relative_path) == ["type"] or (e.validator == "required" and "'type'" in e.message) for e in b
        )
    ]
    if len(type_matched) == 1:
        return [leaf for e in type_matched[0] for leaf in unwrap(e)]
    # If all non-null branches share common error(s) (e.g. Optional[T], non-object
    # value, or a required property common to every branch), report those.
    common = set.intersection(*({sort_key(e) for e in b} for b in non_null))
    if common:
        return [leaf for e in non_null[0] if sort_key(e) in common for leaf in unwrap(e)]
    return [error]


def snapshot(error: ValidationError) -> Error:
    return {"path": error.json_path, "keyword": str(error.validator), "message": error.message}


def write_snapshot(case_file: Path, errors: list[Error]) -> None:
    """Replace (or append) the trailing ``errors:`` block, leaving the rest of the file byte-for-byte intact."""
    text = case_file.read_text(encoding="utf-8")
    pattern = rf"^(?:{re.escape(ERRORS_COMMENT)})?{ERRORS_KEY}:.*"
    head = re.split(pattern, text, maxsplit=1, flags=re.MULTILINE | re.DOTALL)[0]
    if not head.endswith("\n"):
        head += "\n"

    buf = io.StringIO()
    dump_yaml.dump({ERRORS_KEY: errors}, buf)
    case_file.write_text(head + ERRORS_COMMENT + buf.getvalue(), encoding="utf-8")


def test_case_schema_lists_every_schema():
    case_schema = json.loads(CASE_SCHEMA_FILE.read_text(encoding="utf-8"))
    listed = case_schema["properties"]["schema"]["enum"]
    routed = [clause["if"]["properties"]["schema"]["const"] for clause in case_schema["allOf"]]
    expected = [f.name for f in SCHEMA_FILES]
    assert listed == expected, (
        f"{CASE_SCHEMA_FILE.name}: `properties.schema.enum` must list the files in {SCHEMA_DIR}, sorted; "
        f"missing {sorted(set(expected) - set(listed))}, extra {sorted(set(listed) - set(expected))}"
    )
    assert routed == expected, (
        f"{CASE_SCHEMA_FILE.name}: `allOf` needs one if/then clause per file in {SCHEMA_DIR}, sorted "
        f"(copy an existing one); missing {sorted(set(expected) - set(routed))}, extra {sorted(set(routed) - set(expected))}"
    )


@pytest.mark.parametrize("case_file", CASE_FILES, ids=lambda p: p.stem)
def test_schema(case_file: Path, request: pytest.FixtureRequest):
    case = load_yaml.load(case_file)
    assert set(case) - {ERRORS_KEY} == {"description", "schema", "document"}, (
        f"{case_file}: expected keys description, schema, document (and optional {ERRORS_KEY})"
    )

    raw_errors = VALIDATORS[case["schema"]].iter_errors(case["document"])
    errors = sorted((leaf for e in raw_errors for leaf in unwrap(e)), key=sort_key)
    actual = [snapshot(e) for e in errors]

    if request.config.getoption("--update-snapshots"):
        if case.get(ERRORS_KEY) != actual:
            write_snapshot(case_file, actual)
        return

    assert ERRORS_KEY in case, f"{case_file}: no `{ERRORS_KEY}` snapshot yet; run `uv run pytest --update-snapshots`"
    assert case[ERRORS_KEY] == actual, (
        f"{case_file}: snapshot is out of date; run `uv run pytest --update-snapshots` and review the diff"
    )
