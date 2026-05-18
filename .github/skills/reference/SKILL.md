---
name: reference
description: 'Use when implementing a semantic-conventions change, upstream proposal diff, spec change, or new GenAI span or attribute in this repository. Adds reference scenarios, inline attribute emission, and data coverage for every Python library that credibly supports the change.'
---

# Reference Coverage

Use this skill when a semantic-conventions change introduces or changes GenAI spans, attributes, or requirement levels and the repository needs reference coverage across all libraries that support the new behavior.

Per-scenario authoring rules — inline attribute emission, span boundaries, current-call values, public-entry-point usage, and what to ignore — live in [reference-scenarios.instructions.md](../../instructions/reference-scenarios.instructions.md). Follow that file when editing any `reference/scenarios/**/scenario.py`. This skill covers only the agent-level workflow around it.

## Goal

Turn the semantic-conventions change into concrete reference implementations in this repository: scenarios and emitted attributes that honestly exercise every supporting library without faking values the library cannot credibly expose.

## Non-Goals

This skill is not for deciding whether the convention itself is correct.

It is also not the final evaluation pass. After adding reference implementations, consult the evaluation rubric in [evaluate-reference.instructions.md](../../instructions/evaluate-reference.instructions.md) to judge capturability, coverage quality, and honest capture gaps.

## Core Stance

- Start from the semantic-conventions change as written.
- Add reference implementations for every library in this repository that supports the affected operation and can credibly expose the new fields at the current call boundary. Repository-wide coverage across all supporting libraries is the default, not a single illustrative example.
- Do not skip a supported library just because the implementation is repetitive, and do not stop after the first passing library when the same change applies to multiple ecosystems.
- Do not force unsupported libraries to emit guessed, hardcoded, cross-call, or app-specific values.
- Prefer the library's natural execution shape over surgical paths that minimize trace output. Extra LLM round-trips or extra spans produced by invoking the public entry point are acceptable.

## What Counts As Supporting The Change

A library should usually get a reference update when all of the following are true:

1. The repository already has a scenario directory for the library under `reference/scenarios/`. If it does not, the library is `not yet implemented in this repo`, not a supporting library missing coverage.
2. The existing scenario already exercises the relevant operation, or the operation can be added naturally within that scenario's structure.
3. The library API or current response objects expose the information needed for the new span or attribute at the current call boundary.
4. The reference implementation can emit the value from the current request, current response, current exception, or stable library-owned state.

If the value would have to be guessed, carried forward from an unrelated call, or synthesized from test-only scaffolding, do not force it into the reference implementation.

## Procedure

1. Read the semantic-conventions change and extract the exact changed spans, attributes, requirement levels, and examples.
2. Translate it into a concrete implementation worklist grouped by operation, not by prose section.
3. Inventory the Python libraries in this repository that implement the affected operation.
4. For each library, decide whether the changed fields are credibly available from the current call boundary.
5. Add or update the reference scenario for every supporting library following [reference-scenarios.instructions.md](../../instructions/reference-scenarios.instructions.md).
6. Regenerate downstream outputs in dependency order:
   - Refresh each updated scenario's `reference/scenarios/<library>/data.json` by running its scenario.
   - Regenerate `reference/reports/*.md` via `uv run update-reports` (see [reference/README.md](../../../reference/README.md)).
   - If the change also touches `model/**` or `docs/gen-ai/**`, regenerate the registry and docs via `make generate-all` (see `.github/copilot-instructions.md`).
7. Keep unsupported libraries honest. If a library cannot credibly emit a field, leave it out and record it as a capture gap (see [evaluate-reference.instructions.md](../../instructions/evaluate-reference.instructions.md)).
8. Run targeted validation for the changed libraries when feasible.

## Output Format

When using this skill, summarize the work in five groups.

- `Convention changes`
- `Libraries updated`
- `Libraries not updated`
- `Capture gaps`
- `Validation`

Under `Libraries not updated`, state whether each library is:

- `not applicable`
- `not yet implemented in this repo`
- `honest capture gap; evaluate separately`

Under `Capture gaps`, list each library left without a reference implementation and the exact missing current-call source that prevented a credible implementation.
