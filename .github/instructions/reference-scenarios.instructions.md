---
description: "Conventions for reference scenarios under reference/scenarios. Covers inline attribute emission, span boundaries, public-entry-point usage, and what to ignore."
applyTo: "reference/scenarios/**/scenario.py"
---

# Reference scenarios

Reference scenarios are runnable Python instrumentation that prove proposed
GenAI conventions are capturable. They should be easy to scan: a reader
should see, at the instrumentation site, exactly what attributes get emitted
and where each value comes from.

## Attribute and tag emission

- Set emitted attributes and tags inline at the instrumentation site. Do not
  move emission into helper methods such as `setServerTags`,
  `setServerAttributes`, `_set_server_attributes`, or similar wrappers.
- If a method owns its own span boundary, set that span's attributes inline
  in that method.
- Keep base attributes, derived attributes, and result attributes together
  in the same span or activity block.
- Small local parsing or derivation that exists only to support nearby
  emitted attributes is fine; keep it next to the emission.

## Attribute values

- For attributes whose value is not truly static for the scenario, do not
  hardcode the emitted value. Use a local variable or field read from the
  current request or response.
- Request-side attributes such as `gen_ai.request.model` should come from
  the same variable or object field passed into the SDK call.
- Response-side attributes such as `gen_ai.response.model`, response ids,
  finish reasons, and token counts should come from the current response or
  streamed result object, optionally via a small nearby local.
- If the same non-static value is needed in both the SDK call and span
  attributes, bind it once locally and reuse it. Avoid throwaway forwarding
  locals that only mirror an existing constant, argument, or SDK field.

## Span boundaries

- The span must be open around the library invocation. `sampling_relevant`
  request attributes go in the span-start arguments; response attributes are
  set from the returned object inside the same `with` block.
- Capturing the response and then replaying attributes onto a separately
  opened or post-hoc span is a defect even if the final attribute set looks
  correct.

## Library entry points

- Scenarios must call the library's public entry point. Patching private
  methods to open spans around them is acceptable, but the scenario itself
  must not invoke private APIs directly.

## What not to flag in review

- Library-native sibling spans, retries, converter spans, or extra LLM
  round-trips produced by invoking a library's public entry point. These
  are honest reference data, not noise.
