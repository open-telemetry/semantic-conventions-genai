---
applyTo: "model/**/*.yaml"
---

# Requirement-level condition notes

When `conditionally_required:` or `recommended:` carries an inline condition
note, write the note as one or more **complete sentences**: capitalize the
first word and end with a period.

# Links to upstream docs

Model YAML is data, not a template, so a link hardcoded against a specific
upstream ref goes stale on the next version bump. Write links into
open-telemetry/semantic-conventions as `{{upstream_docs_base}}/docs/...`. The
markdown templates substitute the placeholder with the ref pinned by the
`model/manifest.yaml` dependency.
