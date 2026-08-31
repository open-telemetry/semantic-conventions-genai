<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Execution state changes
--->

# GenAI execution state changes

**Status**: [Development][DocumentStatus]

This guidance applies when a GenAI workflow or agent runtime exposes state
updates as deltas. It does not define a new span type, a generic workflow-state
model, or durable execution identity.

Use the `gen_ai.execution.state.changed` event only when the runtime exposes a
non-empty state delta. Record it in the context of the internal workflow or
agent span that observes the update. Do not infer a change by comparing full
state payloads, and do not emit the event for an unchanged snapshot, retry, or
replay.

`gen_ai.execution.state.changed_key.count` records the size of the runtime-owned
delta without exposing the state. `gen_ai.execution.state.changed_keys` is
opt-in. It may contain only bounded, schema-defined key names that are safe to
export. Leave it unset when keys are dynamic or may contain user identifiers,
content, tool arguments, secrets, or other sensitive values.

Record `gen_ai.execution.state.version` only when the runtime exposes a version
for the resulting state. Do not synthesize a version from content, timestamps,
trace or span identifiers, or hashes. State versions are high-cardinality and
MUST NOT be used in metric dimensions, span names, or sampling decisions.

The event describes a runtime-owned state delta, not the state itself. It MUST
NOT contain state values, transition payloads, tool arguments or results, raw
idempotency data, or hidden reasoning.

## Checkpoints, retries, and external effects

Checkpoint storage operations remain owned by the applicable storage
instrumentation. Writing an unchanged checkpoint does not produce
`gen_ai.execution.state.changed`.

Retry attempts, replays, and recovery runs are not interchangeable. This
convention does not define attempt numbering or operation-level retry metrics.
A replay that reconstructs state MUST NOT report an external effect as newly
executed unless the effect was actually attempted again.

Tool spans describe framework-observed tool execution. They do not prove that
an external system was read-only, mutated successfully, deduplicated a request,
or restored a business invariant. HTTP, database, messaging, and other
applicable conventions remain the source of evidence for those operations.
Instrumentations MUST NOT record raw idempotency keys, key-derived hashes, or
deduplication identifiers under these conventions.

Compensation describes an attempted operation, not proof that an earlier
business effect was completely reversed. Instrumentations MUST NOT infer a
compensating operation from tool names, arguments, results, or trace proximity.

## Causal links

OpenTelemetry span links are appropriate when a runtime exposes causal context
that cannot be represented by a parent-child relationship, including work that
continues in another trace. This convention does not assign relationship types
to links. Instrumentations MUST NOT create links from identifiers that are not
OpenTelemetry span contexts or infer causal links from timestamps, names, or
execution identifiers.

Relationship types for resume, retry, delegation, fan-out, aggregation,
tool-decision, and compensation are deferred until the semantic-convention
model can define link-specific attributes and independent runtimes expose
equivalent relationships. Transition reasons and actor identifiers are also
deferred. Application-defined state values are not part of this convention.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
