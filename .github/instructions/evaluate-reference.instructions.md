---
applyTo: "model/**,docs/gen-ai/**,reference/scenarios/**"
---

# Reference evaluation

Judge whether the scenarios in a changeset back its convention changes. Read the
changeset whole: for each field changed under `model/**`, read the scenarios
that should emit it, including ones this PR did not touch.

Scenario rules live in
[reference-scenarios.instructions.md](reference-scenarios.instructions.md).
Flag each violation and name the rule.

## Trace every value

Instrumentation lives inside the library and sees only the library's own API, so
each value must be readable from there: either a parameter the library defines
and interprets, or something the library or mock server returns.

For each attribute the PR adds or changes, name that parameter or return value.
Flag the field when:

- the library only carries the value: it went in through an opaque or
  app-defined payload, and its meaning comes from the scenario's keys or types
- it was read from a type the scenario declares that no library API interprets
- you cannot name the argument, return value, response field, streamed event,
  exception, or library state behind it
- the author states instrumentation cannot derive it, and the scenario emits it
  anyway

Each of these means the field is not demonstrated, however many attribute reads
sit between the literal and the emission. Ask for the emission to be dropped, or
for the field to ship with `(none)` supporting libraries.

Finding the attribute name in a scenario or in `data.json` proves only that a
string was emitted.

## Also flag

- a scenario directory named for the proposed convention instead of the library
- a scenario calling the library's private API directly
- a library whose existing scenario could emit the field and does not

## Classify each field

- `direct` - read at the call boundary: arguments, return values, streamed
  chunks, exceptions, the current client's config
- `derivable` - computed from what the library means, no app-specific guessing
- `weak` - app-specific naming, opaque ids, state cached from another call,
  test-only scaffolding, an enum guessed from free text, or a value the library
  only passes through
- `capture gap` - the library cannot produce it

Judge each library on its own call boundary. Check every library that could
support the change.

## Report

For each `weak`, missing, or `capture gap` field, say why, name the
call-boundary source that would support it, and say whether that source exists
today. Then pick one, preferring the first that fits: `fix implementation`,
`add reference for supporting library`, `leave unchanged; honest capture gap`.

State these separately when they coexist in one review:

- `library reference supports this field`
- `library reference does not support this field`
- `supporting library was never implemented`
