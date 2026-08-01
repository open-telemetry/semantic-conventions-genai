# Contributing to the Reference Scenarios

This directory contains the runnable reference scenarios and the tooling
used to validate them against the GenAI semantic conventions.

If you are changing the semantic conventions themselves under `model/` or
`docs/`, use the repository-level guide in [../CONTRIBUTING.md](../CONTRIBUTING.md).

## Structure

```text
pyproject.toml           # Tooling project metadata
src/
  semconv_genai/         # Shared framework, CLI modules, and mock server
scenarios/
  <library>/             # Reference scenarios
```

Within each scenario directory:

- `scenario.py` — SDK invocation + manual OTel spans
- `pyproject.toml` — Dependencies
- `uv.lock` — Locked transitive dependency graph (committed)
- `data.json` — Committed results

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (uv will fetch the Python 3.12 interpreter declared in `pyproject.toml` on first run).

Run the commands below from this `reference/` directory.

## Running scenarios

First-time setup creates `.venv` and installs the tooling:

```bash
uv sync
```

Run a single library, or all libraries:

```bash
uv run run-scenario openai          # one library
uv run run-scenario --all           # all libraries
uv run run-scenario --all --keep-going   # continue through failures, report at end
```

`uv run run-scenario <library>` runs the selected scenario under
[scenarios/](scenarios/) against a local mock LLM server, validates the
emitted telemetry, and writes the results that feed the checked-in reports.

## Linting

Lint and format the Python code under `src/semconv_genai/` and `scenarios/`:

```bash
uv tool run --from ruff ruff check --fix src/semconv_genai scenarios
uv tool run --from ruff ruff format src/semconv_genai scenarios
```

## Updating reports

Regenerate the checked-in status section in `README.md` after updating committed
`data.json` files:

```bash
uv run update-reports
```

## Contribution expectations

- Keep reference coverage honest. Only emit spans and attributes that the
  library or reference code can actually produce.
- Prefer focused updates to the affected library under `scenarios/<library>/`.
- After regenerating `scenarios/*/data.json`, run `uv run update-reports` and
  commit both alongside your change.

### Which operations a scenario should emit

A scenario emits telemetry only for the operations the library itself performs.
Two principles:

- **Don't re-emit another library's telemetry.** If the library delegates an
  operation to another instrumentable library (for example a framework that
  calls `openai`, `anthropic`, or `google-genai` under the hood),
  instrumentation for that operation belongs to the underlying library.
- **Emit an operation only when the library has that concept.** Emit inference
  or embeddings only when the library is itself the model-call boundary, an
  agent span only when it models agents, a workflow span only when it models
  workflows or graphs, and so on. Calling the provider's REST API directly (with
  no separate instrumentable client library in between) makes the library the
  model-call boundary, so it is a valid reason to emit inference.

Agent-framework instrumentation SHOULD NOT emit inference spans by default; the
underlying LLM library owns them. The exception is a framework that issues the
model call in a way no other instrumentable library can observe — it calls the
REST API directly, embeds a vendored model library, or similar. In that case the
framework is the only place the inference call is visible, so it SHOULD emit the
span.

If a library emits unrelated native telemetry that obscures the intended
validation surface, suppress that library-owned telemetry in the reference
scenario rather than changing the semantic conventions to match it.

## Adding or updating a library

Reference scenarios are both validation inputs and examples for instrumentation
authors, so keep them minimal and readable.

When adding a new reference scenario:

1. Create `scenarios/<library>/scenario.py`.
2. Create `scenarios/<library>/pyproject.toml` declaring the SDK dependencies plus
   `genai-reference-shared` (sourced from the shared project at `shared/`).
   The OTel SDK pin is provided transitively by `genai-reference-shared`; do
   not re-declare it here unless the library needs a non-default version.

   ```toml
   [project]
   name = "<library>-reference-test"
   version = "0"
   requires-python = ">=3.12"
   dependencies = [
       "<sdk>==<pinned-version>",
       "genai-reference-shared",
   ]

   [tool.uv.sources]
   genai-reference-shared = { path = "../../shared", editable = true }

   [tool.uv]
   package = false
   ```

   If the SDK under test requires a specific OTel version that differs
   from the default pin in [shared/pyproject.toml](./shared/pyproject.toml),
   add `override-dependencies` to the existing `[tool.uv]` table:

   ```toml
   [tool.uv]
   package = false
   override-dependencies = [
       "opentelemetry-api==<required>",
       "opentelemetry-sdk==<required>",
       "opentelemetry-exporter-otlp-proto-grpc==<required>",
   ]
   ```

3. Run `uv lock` inside `scenarios/<library>/` to generate the committed
   `uv.lock`. Re-run it whenever you change dependencies; `run-scenario` uses
   `uv sync --frozen` and will fail if the lockfile is stale.
4. Run `uv run run-scenario <library>` to generate `scenarios/<library>/data.json`.
5. Regenerate `README.md` with `uv run update-reports`.
