---
description: "Review guidance for Towncrier changelog fragments."
applyTo: "changelog.d/*.md"
---

# Changelog fragments

Towncrier is configured with `wrap = true`, so generated `CHANGELOG.md` output
is wrapped during release note generation. Changelog fragments should use one
logical line per fragment entry; when reviewing, ask contributors to remove
manual hard wrapping from fragment text.
