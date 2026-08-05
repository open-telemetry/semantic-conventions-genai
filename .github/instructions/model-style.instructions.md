---
applyTo: "model/**/*.yaml"
---

# Requirement-level condition notes

When `conditionally_required:` or `recommended:` carries an inline condition
note, write the note as one or more **complete sentences**: capitalize the
first word and end with a period.

# Links to upstream docs

Write links into open-telemetry/semantic-conventions as ordinary URLs pinned to
a version, e.g. `https://github.com/open-telemetry/semantic-conventions/blob/v1.44.0/docs/...`.
Don't use a template placeholder — this YAML is published as-is and read
directly by other repos. `make generate-all` rewrites the version in every such
link to match the `model/manifest.yaml` dependency, so it stays current on its
own.
