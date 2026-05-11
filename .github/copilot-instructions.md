# Repository conventions

These instructions guide both human contributors and AI assistants
(including GitHub's Copilot code reviewer) working in this repository.

Path-specific guidance lives under `.github/instructions/` and applies
automatically based on the files touched.

## Repository overview

This repo defines the OpenTelemetry GenAI semantic conventions. Changes flow
through several coupled surfaces:

- `model/<namespace>/*.yaml` — source of truth for attributes, spans, metrics,
  and events. All attributes must be defined in `registry.yaml`.
- `docs/gen-ai/` and `docs/registry/` — generated from the model via Weaver
  (`make generate-all`). Generated tables and registry pages should not be
  hand-edited.
- `schema-snapshot/registry.yaml` — committed snapshot, refreshed by
  `make generate-all`.
- `reference/scenarios/<library>/` — runnable Python reference scenarios
  (`scenario.py`) that prove proposed conventions are capturable.

## PR scope

- Keep PRs small and focused. Do not mix unrelated convention changes; see
  the "Keep PRs small" guidance in `CONTRIBUTING.md`.
- Non-editorial convention changes need a `CHANGELOG.md` `Unreleased` entry.
  Editorial-only changes (typos, rewording, tooling) do not need one.
- Convention changes under `model/` or `docs/` need a corresponding update
  under `reference/scenarios/` to demonstrate capturability.

## Code style

- Prefer simple syntax over dense or clever equivalents.
- Do not use `try`/`except` to swallow exceptions. Errors should bubble up
  and fail loudly unless there is a clear reason to handle them.
- Use explicit, descriptive names over compact ones.

## What not to flag in review

- Generated files under `docs/registry/` and `schema-snapshot/registry.yaml`
  — review the model changes that produced them instead.
- Generated tables inside `docs/gen-ai/*.md` — review the model changes
  that produced them instead.
