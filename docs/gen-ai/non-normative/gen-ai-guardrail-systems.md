<!--- Hugo front matter used to generate the OpenTelemetry.io documentation --->
# GenAI guardrail systems

**Status**: [Development][DocumentStatus]

This non-normative document records the systems surveyed while defining the
[GenAI guardrail conventions](../gen-ai-guardrails.md). It summarizes only
properties visible at the instrumented API boundary.

<!-- toc -->

- [Remote guardrail services](#remote-guardrail-services)
- [Dedicated in-process guardrail APIs](#dedicated-in-process-guardrail-apis)
- [General-purpose extension points](#general-purpose-extension-points)
- [Property mapping](#property-mapping)

<!-- tocstop -->

## Remote guardrail services

| System | Operation | Observable request properties | Observable response properties |
| --- | --- | --- | --- |
| Amazon Bedrock Guardrails | `ApplyGuardrail` | guardrail identifier, guardrail version, source, content | action, action reason, output content, assessments |
| Azure AI Content Safety | `analyze_text` | text, requested categories, blocklists | category severities, blocklist matches |
| Google Model Armor | `sanitize_user_prompt`, `sanitize_model_response` | template, prompt or model response | match state, invocation state, filter results, errors, optional deidentified content |

These operations provide concrete remote client boundaries for
`gen_ai.apply_guardrail.client` spans.

## Dedicated in-process guardrail APIs

| Library | Dedicated guardrail boundary | Observable result |
| --- | --- | --- |
| OpenAI Agents | Input, output, tool-input, and tool-output guardrails | guardrail name, tripwire state, output information |
| OpenAI Guardrails | Configured input and output guardrails | guardrail name, pipeline stage, tripwire state, result information |
| Guardrails AI | `Guard.validate()` | validation outcome and validated output |
| NeMo Guardrails | `LLMRails.generate()` | guarded generation result; independent per-rail results are not consistently exposed at the public boundary |

Dedicated local APIs can emit `gen_ai.guardrail.result` events. This proposal
does not define an internal guardrail span.

## General-purpose extension points

Claude Agent SDK hooks, Google ADK callbacks, and LangChain middleware can run
arbitrary application logic. The extension point does not identify whether the
callback implements a guardrail, logging, mutation, or another concern.
Instrumentation therefore cannot classify these callbacks as guardrails without
application-specific knowledge.

## Property mapping

| Attribute | Observable source |
| --- | --- |
| `gen_ai.guardrail.component.name` | SDK service or dedicated guardrail name |
| `gen_ai.guardrail.result.type` | Native result field or result kind, such as `action`, `severity`, `filter_match_state`, or `tripwire_triggered` |
| `gen_ai.guardrail.result.value` | Native result value without translation to a generalized verdict |
| `gen_ai.guardrail.result.reason` | Native reason or explanation, when returned |
| `gen_ai.guardrail.source` | Native request source, stage, or dedicated operation |
| `gen_ai.guardrail.policy.id` | Policy, guardrail, or template identifier accepted by the API |
| `gen_ai.guardrail.policy.version` | Policy or guardrail version accepted by the API |
| `gen_ai.guardrail.policy.rule.id` | Native rule, filter, detector, or blocklist identifier |
| `gen_ai.guardrail.risk.category` | Native category or filter name |
| `gen_ai.guardrail.risk.score` | Native severity, confidence, or risk score with its provider-defined scale |
| `gen_ai.guardrail.content.input.value` | Content passed to the SDK operation |
| `gen_ai.guardrail.content.output.value` | Content returned by the SDK operation |

Not every system exposes every property. Instrumentation records only values
available at its API boundary and does not infer caller enforcement, policy
identity, or normalized verdicts from categories and scores.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
