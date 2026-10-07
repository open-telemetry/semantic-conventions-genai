# JSON schema snapshot tests

Sample documents validated against the committed JSON schemas in
[`model/gen-ai/`](../../../../model/gen-ai/), with the errors each schema
reports snapshotted alongside. They catch unintended changes to what a schema
accepts or rejects, and document the intended behaviour by example.

```bash
make test-json-schemas                 # from the repo root
uv run pytest                          # from docs/gen-ai/non-normative
uv run pytest --update-snapshots       # refresh the `errors:` blocks
```

## Adding a case

Create `cases/<case>.yaml` with a `description`, the `schema` file name under
`model/gen-ai/`, and the `document` to validate. Write the document as JSON
(valid YAML) so it can be pasted to and from the spec examples and real
telemetry:

```yaml
# yaml-language-server: $schema=../case.schema.json
description: Every message needs `role` and `parts`
schema: gen-ai-input-messages.json
document: [
  { "role": "user" }
]
```

The first line points editors with YAML language server support (VS Code's
YAML extension, for example) at [`case.schema.json`](case.schema.json), which
describes the case file and routes `document` to the schema named by `schema`.
That gives completion and hover docs for the document's fields, and live
validation squiggles that match what the test reports. If you want completion
while drafting, block-style YAML gets better results than JSON; either is
accepted.

Then run `uv run pytest --update-snapshots`. The runner appends an `errors:`
block with what the schema reports and leaves the rest of the file untouched.
Review it: an empty list means the document is valid.

```yaml
errors:
  - path: $[0]
    keyword: required
    message: "'parts' is a required property"
```

Each error records the JSON path of the offending value, the failing keyword,
and the validator's message. For `anyOf` unions (nullable fields, message parts,
tool definitions), when a single branch's `type` matches or all branches fail
the same way, that branch's errors are recorded directly instead of the outer
`anyOf` failure.

When a schema change alters the errors, the plain `uv run pytest` run fails
with a diff. Re-run with `--update-snapshots` and review the changed case files
in the PR. A case whose `errors:` goes from `[]` to non-empty means documents
that used to validate no longer do: that is a breaking change and needs a
`breaking` changelog fragment.

Keep `errors:` as the last top-level key; the updater rewrites everything from
that line to the end of the file.

## Adding a schema

When a new `model/gen-ai/*.json` file appears, register it in
[`case.schema.json`](case.schema.json): add the file name to
`properties.schema.enum` and copy one of the `allOf` clauses so `document` is
routed to it. `test_case_schema_lists_every_schema` fails until both are in
place. Then add at least one case for it.
