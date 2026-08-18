# openai-guardrails reference scenario

Real-library reference implementation for the **base** `run_guardrail` span,
using [`openai-guardrails`](https://pypi.org/project/openai-guardrails/) (import
name `guardrails`).

## What it demonstrates

Generic instrumentation wraps two framework seams and emits one base
`gen_ai.run_guardrail.internal` span per guardrail evaluation, deriving every
base attribute from framework-owned runtime state:

| Attribute | Source at the `ConfiguredGuardrail.run` boundary |
| --- | --- |
| `gen_ai.guardrail.component.name` | `self.definition.name` |
| `gen_ai.guardrail.target.type` | pipeline stage (`pre_flight`/`input` -> `input`, `output` -> `output`) |
| `gen_ai.guardrail.target.subtype` | `llm` |
| `gen_ai.guardrail.verdict.type` | `deny` if `tripwire_triggered` else `allow` |
| `gen_ai.guardrail.action.type` | `block` if the tripwire fires (call is raised/blocked) else `allow` |
| `gen_ai.guardrail.verdict.reason` | `GuardrailResult.info["reason"]` when present |
| `error.type` | from `GuardrailResult.execution_failed` |

The scenario drives the library through its **public** entry point
(`GuardrailsOpenAI(...).chat.completions.create(...)`) against the local mock
LLM server, running one benign call (guardrails allow) and one call whose input
trips a local email/PII guardrail (framework blocks the call).

## Capture gap (intentional)

This scenario does **not** emit the `gen_ai.guardrail.security.finding` event or
the `gen_ai.guardrail.security.*` overlay. The framework's runtime does not
expose a policy identity (`gen_ai.guardrail.security.policy.id` is *required* on
the finding event), an external finding id, or a standardized risk
classification — a check's `info` dict is freeform. That gap is the evidence
for keeping the security overlay separable from the base tier. The hand-authored
`openai` scenario still exercises the full security overlay for model coverage.

## Instrumentation seams (validated against `openai-guardrails` 0.3.0)

- `guardrails.runtime.run_guardrails` / `guardrails.client.run_guardrails` —
  wrapped to record the library-owned `stage_name` in a context var (the only
  place the pipeline stage is visible). Context vars copy into the per-check
  asyncio tasks, so each check reads the correct stage.
- `guardrails.runtime.ConfiguredGuardrail.run` — the per-check execution
  boundary; wrapping the class method yields one correctly-timed span per
  guardrail, independent of how the client imported `run_guardrails`.

A fully-local custom regex guardrail is registered via
`default_spec_registry.register(...)` so the check runs offline and
deterministically (the mock server serves only chat/completions, embeddings,
and responses — not the endpoints LLM-backed built-ins expect). The check being
custom does not weaken capturability: the instrumentation reads only
framework-owned runtime state, never the check internals.

## Running / validation

Validated end-to-end against `openai-guardrails` 0.3.0 (Weaver live-check exit
0; base guardrail attributes captured, `data.json` committed):

```bash
cd reference
uv run run-scenario openai-guardrails
uv run update-reports
```
