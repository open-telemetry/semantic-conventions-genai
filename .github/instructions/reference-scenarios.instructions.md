---
applyTo: "reference/scenarios/**"
---

# Reference scenarios

A scenario is evidence that a real library, driven through its public API,
produces the data a convention asks instrumentation to record. A reader should
see, at the emission site, which library expression produced each value.

## Which library

- One directory per library, named for the library or SDK it drives: `openai`,
  `langchain`, `google-adk`.
- Put new behavior in the scenario of a library that already has it.
- Drive the library's real feature: for an approvals convention, run the
  library's approval API; for interrupts, run its interrupt API and let its own
  objects carry the outcome.
- Call the library's public entry point. Patching private methods to open spans
  around them is fine.

## Where values come from

Instrumentation lives inside the library and sees only the library's own API.
Every emitted value must be readable from there, so it comes from one of two
places:

- input the scenario passes through a parameter the library defines and
  interprets: `model=`, `tools=`, an agent's `name=`
- output the library or the mock server returns: response model, ids, finish
  reasons, token counts, a checkpoint id from `get_state`

`x = obj.field` counts when the library defined `obj` and gave `field` its
meaning. Bind a value needed by both the SDK call and the span once, and reuse
it. Small local parsing feeding a nearby attribute is fine; keep it at the
emission site.

A value is a literal when the library only carries it - when the meaning lives
in the scenario's own keys, dict shape, or classes rather than in the library's
API:

- `interrupt({"reason": "human_input"})` then emitting `intr.value["reason"]`:
  `interrupt()` takes any payload, and `reason` is the scenario's key
- `Command(resume={"approved": True})` driving an emitted `resolution: approved`:
  the resume value is opaque to the library
- fields of a `Gate`, `Decision`, or `Result` type the scenario declares and no
  library API reads
- a clock set past a deadline the scenario chose
  (`now = deadline + timedelta(minutes=1)`), making the branch always true

Noting any of this in a comment or README leaves it a literal.

## How attributes are set

- Set attributes inline at the emission site, not in helpers like
  `_set_request_attributes`.
- Keep the span open around the library call. `sampling_relevant` request
  attributes go in the `attributes` argument to `start_as_current_span`; the
  rest, and all response attributes, go inside the same `with` block.
- Keep base, derived, and result attributes on the same span.
- A method that owns a span sets that span's attributes inline.

## Honest reference data

Sibling spans the library itself emits - retries, converter spans, worker tasks,
fall-through paths, extra LLM round-trips from a public entry point.

## After editing

Regenerate the scenario's `data.json` and the affected `reference/reports/*.md`
per [reference/README.md](../../reference/README.md) before pushing. CI enforces
that generated output matches the scenario.
