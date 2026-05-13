---
name: evaluate-reference
description: 'Use when reviewing completed reference scenarios, scenario outputs, or data results against a semantic-conventions PR, upstream proposal, or spec change. Evaluates reference coverage, capturability, direct observability, derivable fields, missing supporting libraries, and honest capture gaps without forcing fake compliance.'
argument-hint: 'Describe the semantic-conventions PR and the reference implementation, files, or results to evaluate.'
---

# Reference Evaluation

Use this skill after reference scenarios have been added for a semantic-conventions PR and the repository needs an evaluation of coverage quality and capturability.

## Goal

Determine whether the resulting reference implementation honestly shows what each library can emit while mirroring the semantic-conventions PR as written.

## Non-Goal

This skill is not for arguing that the upstream proposal is correct or incorrect.

Its job is to evaluate the resulting reference set:

- which libraries genuinely demonstrate the proposed behavior
- which emitted fields are direct, derivable, weak, or unsupported
- which missing fields are honest capture gaps rather than implementation bugs
- which supporting libraries still need reference coverage

## Evaluation Stance

In this repository, a mismatch between a proposed semantic convention and a believable reference implementation is not automatically a bug in the implementation.

It may indicate a real capture gap between the proposal and what native instrumentation for that library can credibly emit.

Default to these principles:

- Preserve the semantic-conventions PR as the evaluation target.
- Judge each library on what its current call boundary honestly exposes.
- Distinguish `implementation needs fixing` from `library does not demonstrate this field`.
- Prefer honest capture gaps over superficial compliance.
- Evaluate coverage across all supporting libraries, not just the first one that passes.

## Core Rule

Do not ask only whether an attribute appears in the reference output.

Ask whether native instrumentation for the underlying library can populate it correctly and consistently from information the library already owns.

If you cannot name the concrete argument, object, response field, streamed event, exception, or library-owned state that would produce the value, treat the field as not credibly demonstrated.

## Attribute Classes

Classify each candidate field as one of:

### 1. Directly Observable

The instrumentation can read it from the current call boundary.

Typical sources:
- method arguments
- return values
- streamed chunks or events
- exceptions
- client configuration
- current request or response objects

### 2. Semantically Derivable

The instrumentation can compute it from library-owned semantics without app-specific guesswork.

This includes normalized values that are not literal field copies, as long as the derivation is stable and grounded in the library contract.

### 3. Too Weak Or App-Specific

Flag it if it depends on app-specific naming, opaque identifiers, cached data from another call, test-only scaffolding, or guessing a semantic enum from arbitrary strings.

## Coverage Questions

1. Does the reference set mirror the semantic-conventions PR accurately?
2. Which libraries in this repository support the affected operation?
3. Which of those libraries were implemented?
4. For each reference implementation, what exact current-call source backs every emitted field?
5. Are any fields missing even though the current library boundary exposes them?
6. Are any emitted fields weak because they rely on cross-call memory or test-only assumptions?

## Review Procedure

1. Read the semantic-conventions PR and reduce it to the spans and attributes that should be evaluated.
2. List the libraries in this repository that support the affected operation.
3. Confirm which of those libraries received reference updates.
4. For each updated library, list each emitted span and attribute.
5. Mark each attribute as `direct`, `derivable`, or `weak`.
6. For each missing or weak field, decide whether:
   - the implementation should be fixed because the SDK call already exposes the data
   - the implementation should remain unchanged because the library does not credibly demonstrate the field
7. For each library that was not implemented, decide whether it is out of scope, not yet implemented here, or a missed supporting library.
8. Prefer these outcomes in order: `fix implementation` -> `add missing supporting library` -> `leave unchanged; honest capture gap`.

## Implementation Defects To Flag

Beyond attribute coverage, flag these implementation-shape defects:

- **Span not wrapping the SDK call.** The span must be open around the library invocation, with request attributes set inline before the call and response attributes set from the returned object inside the same `with` / `using` block. A scenario that captures the response, closes (or never opened) the span, and then replays attributes onto a separately-opened or post-hoc span is a defect, even if the final attribute set looks correct.
- **Private API as scenario entry point.** The scenario must invoke the library's public API. Patching private methods to open spans around them is acceptable, but the scenario calling private methods directly is a defect — it does not credibly demonstrate what native instrumentation could capture.

## Not Defects

Do not flag these as problems:

- **Library-native sibling spans.** Extra spans produced by the library's natural execution shape — worker tasks that run after planning, retries, converters, fall-through paths — are honest reference data, not noise. If invoking the public entry point produces extra LLM round-trips beyond the one being demonstrated, accept them.

## Determining the PR Changeset

Use `gh pr diff <number>` (not `git diff main`) to get the changeset. A stale local `main` causes `git diff main` to include unrelated commits.

## Do Not Conflate

Keep these judgments separate:

- `semantic-conventions PR mirrored correctly`
- `library reference supports this field`
- `library reference does not support this field`
- `supporting library was never implemented`

A correct evaluation can say all of the following at once:

- the repository is targeting the right proposal
- one library implementation should be fixed
- another library honestly cannot emit the field
- a third supporting library still needs reference coverage

## Output Format

When using this skill in a review, summarize the result in five groups.

- `Credible reference coverage`
- `Semantically derivable fields`
- `Too app-specific or cross-call`
- `Missing supporting library implementations`
- `Evaluation recommendation`

For each flagged field or missing library, state:

- why it is weak, missing, or incomplete
- the exact current-call source that would be needed to support it
- whether that source is actually available in the library example

Under `Evaluation recommendation`, use one or more of:

- `fix implementation`
- `add reference for supporting library`
- `leave unchanged; honest capture gap`
