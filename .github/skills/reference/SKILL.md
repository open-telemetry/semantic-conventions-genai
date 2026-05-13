---
name: reference
description: 'Use when implementing a semantic-conventions PR, upstream proposal diff, spec change, or new GenAI span or attribute in this repository. Adds reference scenarios, inline attribute emission, and data coverage for every Python library that credibly supports the change.'
argument-hint: 'Describe the semantic-conventions PR or the convention changes that need reference coverage.'
---

# Reference Coverage

Use this skill when a semantic-conventions PR introduces or changes GenAI spans, attributes, or requirement levels and the repository needs reference coverage across all libraries that support the new behavior.

## Goal

Turn a semantic-conventions PR into concrete reference implementations in this repository.

The result should be a set of reference scenarios and emitted attributes that honestly exercise every supporting library without faking values that the library cannot credibly expose.

## Non-Goals

This skill is not for deciding whether the upstream proposal is correct.

This skill is also not the final evaluation pass. After adding the reference implementations, use the `evaluate-reference` skill to judge capturability, coverage quality, and honest capture gaps.

## Core Stance

- Start from the semantic-conventions PR as written.
- Add reference implementations for every library in this repository that supports the affected operation and can credibly expose the new fields at the current call boundary.
- Do not skip a supported library just because the implementation is repetitive.
- Do not force unsupported libraries to emit guessed, hardcoded, cross-call, or app-specific values.
- Prefer broad, consistent reference coverage across ecosystems when the same library behavior exists.

## What Counts As Supporting The PR

A library should usually get a reference update when all of the following are true:

1. The repository already has a test scenario for the relevant operation, or the operation can be added naturally within that library's existing reference scenario structure.
2. The library API or current response objects expose the information needed for the new span or attribute.
3. The reference implementation can emit the value from the current request, current response, current exception, or stable library-owned state.

If the value would have to be guessed, carried forward from an unrelated call, or synthesized from test-only scaffolding, do not force it into the reference implementation.

## Implementation Rules

When editing reference tests in this repository:

- Open the span **around** the SDK call, not after it. Put available `sampling_relevant` request attributes in the span-start `attributes` / `tags` argument. Then invoke the library inside the `with` block and set response attributes from the returned object inside the same `with` block. Do not capture a completion and replay attribute emission against it after the span has closed or against a separately-opened span.
- When the library's public entry point does not expose the operation directly (for example, an internal-only span boundary inside a library helper), it is acceptable to patch the library's private methods to open spans around them. The scenario itself must still invoke the **public** API. Do not call private methods directly from the scenario.
- Emit attributes inline at the span or activity site.
- Keep request, derived, and response attributes close together.
- Emit non-`sampling_relevant` request attributes inline after the span/activity has started. Keep response values, generated IDs, token usage, output messages, retrieval results, and tool results after the operation that produces them.
- Reuse the same current-call variable that the SDK call uses when emitting request attributes.
- Read response values from the current response or streamed result object.
- Avoid helpers that hide emitted attributes.
- Prefer simple, explicit instrumentation over abstractions.
- Do not introduce throwaway local variables (e.g. `request_model = AGENT_MODEL`) just to forward a constant or SDK field into both the SDK call and a span attribute. Pass the existing constant, argument, or response field directly in both places. Only add a local when the same value is genuinely reused across multiple distinct expressions or needs a derivation step.

## Procedure

1. Read the semantic-conventions PR and extract the exact changed spans, attributes, requirement levels, and examples.
2. Translate the PR into a concrete implementation worklist grouped by operation, not by prose section.
3. Inventory the Python libraries in this repository that implement the affected operation.
4. For each library, decide whether the changed fields are credibly available from the current call boundary.
5. Add or update the reference scenario for every supporting library.
6. Emit the new reference attributes inline and keep them tied to current request or response values.
7. Update the corresponding outputs such as `data.json` and any generated result artifacts required by the repo workflow.
8. Keep unsupported libraries honest. If a library cannot credibly emit a field, leave it out and record that it will need evaluation as a capture gap.
9. Run targeted validation for the changed libraries when feasible.

## Coverage Expectations

The default expectation is repository-wide reference coverage for all supporting libraries, not a single illustrative example.

When the same semantic-convention change applies to multiple ecosystems, look for parallel implementations instead of stopping after the first passing library.

Prefer the library's natural execution shape over surgical paths that minimize trace output. Sibling spans from worker tasks, retries, converters, fall-through paths, and similar library-native behavior are honest reference data, not noise to suppress. If invoking the public entry point produces extra LLM round-trips or extra spans beyond the one being demonstrated, accept them.

## Output Format

When using this skill, summarize the work in four groups.

- `PR changes`
- `Libraries updated`
- `Libraries not updated`
- `Validation`

Under `Libraries not updated`, state whether each library is:

- `not applicable`
- `not yet implemented in this repo`
- `honest capture gap; evaluate separately`

If any library was intentionally left without a reference implementation, explain the exact missing current-call source that prevented a credible implementation.
