---
applyTo: "model/**,docs/gen-ai/**,reference/scenarios/**"
---

# Reference evaluation

Judge whether the scenarios in a changeset back its convention changes. Read the
changeset as a whole: for each field changed under `model/**`, read the scenarios
that should emit it, including ones this PR did not touch.

Scenario authoring rules and examples live in
[.github/skills/reference/SKILL.md](../skills/reference/SKILL.md).
Flag each violation.

## Trace every value

Instrumentation lives inside the library and sees only the library's own API, so
each value must be readable from there: a parameter the library defines and
interprets, something the library or mock server returns, an exception, or
library state.

For each attribute or signal the PR adds or changes, name that parameter or
return value.
Flag the field when:

- it was read from a type the scenario declares that is not passed to the library API
- you cannot name the argument, return value, response field, streamed event,
  exception, or library state behind it

Each of these means the field is not demonstrated, however many attribute reads
sit between the literal and the emission. Ask for the emission to be dropped.

Finding the attribute name in a scenario or in `data.json` proves only that a
string was emitted.

## Also flag

- a scenario that does not apply to a specific library
- a scenario that instruments an arbitrary group of methods (i.e. span boundaries don't match specific library API)
- a scenario that could emit an attribute or a signal but does not
- a field, span, metric, or event added under `model/**` that no scenario in
  the repo emits - name the libraries that should have covered it or suggest to 
  remove it from the changeset if no library can cover it.
