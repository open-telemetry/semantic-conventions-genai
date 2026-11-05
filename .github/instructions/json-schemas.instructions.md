---
applyTo: "docs/gen-ai/non-normative/**,model/gen-ai/*.json"
---

# JSON schemas and their snapshot tests

`model/gen-ai/*.json` are generated from `docs/gen-ai/non-normative/models.py`
by `make generate-json-schemas`; never hand-edit them. Review the `models.py`
change that produced them. Sample documents under
`docs/gen-ai/non-normative/tests/cases/` are validated against the schemas by
`make test-json-schemas`, with the errors each schema reports snapshotted in the
case file's `errors:` block (see `docs/gen-ai/non-normative/tests/README.md`).

## Reviewing a schema change

- Snapshot changes are the behaviour change. Read every modified `errors:`
  block and check it is the intended effect of the `models.py` diff.
- A case whose `errors:` goes from `[]` to non-empty means documents that
  validated before no longer do. That is a breaking change: require a
  `breaking` changelog fragment and a reason in the PR description.
- A case going from non-empty to `[]` loosens the schema. Check that this is
  deliberate and not a union branch (for example `GenericPart`) silently
  accepting malformed documents.
- New schema behaviour needs a case that exercises it: a valid document that
  uses the new field or part type, and where the change restricts something,
  an invalid document that shows the restriction.
- Don't flag the `errors:` blocks for wording or style; they are written by
  `uv run pytest --update-snapshots` and must not be hand-edited.
