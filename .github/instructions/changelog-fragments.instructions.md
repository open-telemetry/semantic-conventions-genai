---
description: "Review guidance for Towncrier changelog fragments."
applyTo: "changelog.d/*.*.md"
---

# Changelog fragments

Valid fragment types are:

- `breaking` - breaking changes
- `deprecation` - deprecations
- `component` - new components
- `enhancement` - enhancements
- `bugfix` - bug fixes
- `clarification` - clarifications

Towncrier is configured with `wrap = true`, so generated `CHANGELOG.md` output
is wrapped during release note generation. Changelog fragments should use one
logical line per fragment entry; when reviewing, ask contributors to remove
manual hard wrapping from fragment text.
