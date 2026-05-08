# Copilot code review instructions

These instructions guide GitHub's built-in Copilot code reviewer for PRs in
this repository. Keep review comments focused, actionable, and specific to
the diff.

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
- `reference/scenarios/<library>/` — runnable Python reference instrumentation
  (`scenario.py`) that proves proposed conventions are capturable.
- `CHANGELOG.md` — non-editorial convention changes need an `Unreleased`
  entry.

## What to flag

### Model and docs consistency

- Stability, requirement level, brief, or examples that disagree between the
  model and the hand-written prose docs under `docs/gen-ai/`.

### Changelog and PR scope

- Non-editorial convention changes missing a `CHANGELOG.md` `Unreleased`
  entry. Editorial-only changes (typos, rewording, tooling) do not need one.
- PRs that mix unrelated convention changes; suggest splitting per the
  "Keep PRs small" guidance in `CONTRIBUTING.md`.

### Reference scenarios (`reference/scenarios/**/scenario.py`)

- Convention changes under `model/` or `docs/` with no corresponding update
  under `reference/` to demonstrate capturability.
- Attribute or tag emission moved into helper methods such as
  `setServerTags`, `setServerAttributes`, `_set_server_attributes`, or
  similar wrappers. Reference instrumentation must set emitted attributes
  inline at the instrumentation site so reviewers can see what is emitted.
- Hardcoded values for attributes that are not truly static for the scenario.
  Request-side attributes such as `gen_ai.request.model` should come from the
  same variable passed into the SDK call. Response-side attributes
  (`gen_ai.response.model`, response ids, finish reasons, token counts)
  should come from the current response or streamed result object.
- The same non-static value bound to two different locals for the SDK call
  and span attributes; it should be bound once and reused.
- Throwaway forwarding locals that only mirror an existing constant,
  argument, or SDK field into both an SDK call and span attributes.
- Spans that do not wrap the SDK call. The span must be open around the
  library invocation: `sampling_relevant` request attributes go in the
  span-start arguments, and response attributes are set from the returned
  object inside the same `with` / `using` block. Capturing the response and
  then replaying attributes onto a separately-opened or post-hoc span is a
  defect even if the final attribute set looks correct.
- Scenarios that invoke the library's private API directly. Patching private
  methods to open spans around them is acceptable, but the scenario itself
  must call the public entry point.

### Code style across the repo

- Advanced or dense syntax where a simpler equivalent exists.
- `try`/`except` that swallows exceptions. Errors should bubble up and fail
  loudly unless there is a clear reason to handle them.
- Unclear or compact names where explicit names would read better.

## What not to comment on

- Generated files under `docs/registry/` and `schema-snapshot/registry.yaml`,
  and generated tables inside `docs/gen-ai/*.md` — review the model changes
  that produced them instead.
- Do not flag library-native sibling spans, retries, converter spans, or
  extra LLM round-trips produced by invoking a library's public entry point.
  These are honest reference data, not noise.
