---
description: "Rubric for evaluating whether semantic-convention changes are supported by reference scenarios."
applyTo: "model/**,docs/gen-ai/**,reference/scenarios/**"
---

# Reference Evaluation

Use when evaluating whether semantic-convention changes are supported by reference scenarios.

Goal: for each attribute changed under `model/**`, confirm at least one reference scenario credibly demonstrates it; for each scenario change, confirm it mirrors the model. Flag any changed attribute with no scenario coverage as `add reference for supporting library`.

A missing or partial reference is not automatically an implementation bug. It may be a capture gap: a legitimate limitation in what the library exposes from its public call boundary.

## Evaluation Stance

- Judge each library on what its current call boundary honestly exposes.
- Distinguish `implementation needs fixing` from `library cannot demonstrate this field`.
- Prefer honest capture gaps over superficial compliance.
- Evaluate coverage across all supporting libraries, not just the first that passes.

## Core Rule

Ask whether native instrumentation can populate the attribute correctly and consistently from information the library already owns at the current call boundary. If you cannot name the concrete argument, return value, response field, streamed event, exception, or library-owned state that produces the value, treat the field as not credibly demonstrated.

## Attribute Classes

Classify each candidate field and tag inline comments accordingly:

- `direct` — readable from the call boundary: arguments, return values, streamed chunks, exceptions, request/response objects, or configuration of the current client.
- `derivable` — computable from library-owned semantics without app-specific guesswork.
- `weak` — depends on app-specific naming, opaque ids, cached state from another call, test-only scaffolding, or guessing an enum from arbitrary strings.
- `capture gap` — the model asks for something the library boundary cannot honestly produce.

## For Each Weak, Missing, Or Capture-Gap Field

State:

- why it is weak, missing, or a capture gap
- the exact current-call source that would be needed to support it
- whether that source is actually available in the library example

Then recommend one of: `fix implementation`, `add reference for supporting library`, `leave unchanged; honest capture gap`. Prefer them in that order.

## Implementation Defects To Flag

See [reference-scenarios.instructions.md](reference-scenarios.instructions.md) for the positive form of these rules; violations are defects.

- **Span not wrapping the SDK call.** The span must be open around the library invocation, with request attributes set inline before the call and response attributes set from the returned object inside the same `with` block. Setting attributes on a separately opened or post-hoc span after the call returns is a defect even if the final attribute set looks correct.
- **Private API as scenario entry point.** The scenario must invoke the library's public API. Patching private methods to open spans around them is acceptable, but the scenario calling private methods directly is a defect — it does not credibly demonstrate what native instrumentation could capture.

## Not Defects

- **Library-native sibling spans.** Library-native sibling spans, retries, converter spans, worker tasks, fall-through paths, or extra LLM round-trips produced by invoking a library's public entry point are honest reference data, not noise.

## Do Not Conflate

Keep these judgments separate, and state them separately when they coexist:

- `library reference supports this field`
- `library reference does not support this field`
- `supporting library was never implemented`

A correct evaluation can say at once: one library should be fixed; another cannot emit the field; a third supporting library still needs reference coverage.
