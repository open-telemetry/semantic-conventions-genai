<!--- Hugo front matter used to generate the OpenTelemetry.io documentation --->
# GenAI Guardrail Systems: Evaluated Systems and Attribute Mapping

**Status**: [Development][DocumentStatus]

This is a non-normative companion to the [GenAI guardrail conventions](gen-ai-security.md).
It records which guardrail systems were surveyed while defining the
`gen_ai.guardrail.*` attributes, which properties each system exposes at a
boundary an instrumentation can observe, and how those properties map onto the
attributes. It exists to answer a review request: list the systems evaluated and
show how their properties map to the conventions.

The goal is to show that the base guardrail attributes are capturable by generic
instrumentation across several unrelated systems, and that the security overlay
attributes depend on system-specific knowledge and are therefore opt-in.

<!-- toc -->

- [Systems evaluated](#systems-evaluated)
- [What each system exposes](#what-each-system-exposes)
- [Property to attribute mapping](#property-to-attribute-mapping)
- [Capturability findings](#capturability-findings)
- [Gaps](#gaps)

<!-- tocstop -->

## Systems evaluated

The survey covered in-process guardrail libraries, hosted guardrail services, and
standalone detection engines. The question for each was: does the system expose
a public boundary where a generic instrumentation could read the guardrail
decision at runtime?

| System | Kind | Guardrail boundary | Standard guardrail span today? |
|---|---|---|---|
| OpenAI Guardrails (`openai-guardrails`) | In-process library | `GuardrailsOpenAI` wrapper runs a configured input/output pipeline; each check returns a `GuardrailResult` | No |
| NVIDIA NeMo Guardrails | In-process library | Rails run inside `generate()`; per-rail result is less structured at the public boundary | No |
| Guardrails AI (`guardrails-ai`) | In-process library | `Guard.validate()` returns pass/fail plus validated output per validator | No |
| AWS Bedrock Guardrails | Hosted service | Guardrail outcome returned on the `bedrock` client response (`amazon-bedrock-guardrailAction`, assessments) | No |
| Azure AI Content Safety | Hosted service | SDK response returns categories and severities | No |
| Detection engines (LLM Guard, Prompt Guard, Llama Guard, Lakera, Rebuff, Vigil) | Detector | Return a label and score; the caller wraps them | No |

No system emits a standardized guardrail span today, which is the gap these
conventions address. Every system does, however, expose a decision at a boundary
an instrumentation can read, which is what makes the base attributes capturable.

## What each system exposes

- **OpenAI Guardrails.** A drop-in client wrapper intercepts
  `chat.completions.create()` and `responses.create()`, runs the configured
  guardrails per stage (input, output), and returns a `GuardrailResult` per check
  (`tripwire_triggered`, `info`, `execution_failed`). On a tripwire the wrapper
  raises, so the same boundary owns both the verdict and the enforced action.
- **NeMo Guardrails.** Rails execute inside `generate()`. Whether a rail fired is
  observable, but the per-rail verdict and reason are not consistently structured
  at the public boundary.
- **Guardrails AI.** `Guard.validate()` returns a pass/fail outcome and the
  validated (optionally fixed) output for each validator, so verdict and a
  modified-content signal are both readable.
- **AWS Bedrock Guardrails.** The model response carries the guardrail action and
  a structured assessment (topic, content, sensitive-information filters), which
  maps to verdict, action, risk category, and policy identity.
- **Azure AI Content Safety.** The SDK response returns per-category severities,
  which map to a verdict and a risk category or score.
- **Detection engines.** Each returns a label and a score. There is no wrapper
  and no enforcement, so the caller supplies target, action, and policy context.

## Property to attribute mapping

The base attributes describe the guardrail itself and are populated from
properties every surveyed system exposes. The
[`gen_ai.guardrail.security.*`](gen-ai-security.md) overlay describes a security
finding and is populated only where a system surfaces that information.

### Base attributes

| Attribute | Populated from |
|---|---|
| `gen_ai.guardrail.component.name` | Configured check or service name (`Moderation`, `Contains PII`, `Bedrock Guardrails`, `Azure Content Safety`) |
| `gen_ai.guardrail.target.type` | Pipeline stage being evaluated (`input`, `output`) |
| `gen_ai.guardrail.target.subtype` | What is guarded (`llm` for prompt/response; `tool_call` for tool arguments or results) |
| `gen_ai.guardrail.target.id` | Identifier of the guarded item, when the boundary has one (for example a tool call id) |
| `gen_ai.guardrail.verdict.type` | The decision: OpenAI Guardrails `tripwire_triggered`, Guardrails AI pass/fail, Bedrock action, Azure severity threshold |
| `gen_ai.guardrail.verdict.reason` | Human-readable reason (`info["reason"]`, flagged category, assessment detail) |
| `gen_ai.guardrail.verdict.code` | Provider-specific code, when present |
| `gen_ai.guardrail.action.type` | Enforcement by the caller (`block` on a raised tripwire; `modify` when a validator rewrites content; `allow` otherwise) |

### Security overlay attributes

| Attribute | Populated from | Typical source systems |
|---|---|---|
| `gen_ai.guardrail.security.risk.category` | Detected risk mapped to a category (OWASP LLM Top 10 or provider label) | Bedrock assessments, Azure categories, detector labels |
| `gen_ai.guardrail.security.risk.score` | Normalized confidence or severity | Azure severities, moderation scores, detector scores |
| `gen_ai.guardrail.security.policy.id` | Policy identity | Bedrock guardrail id, org policy id |
| `gen_ai.guardrail.security.policy.rule.id` | Specific rule, filter, or detector within the policy | Bedrock filter, validator name, detector name |
| `gen_ai.guardrail.security.content.input.value` / `.output.value` | Evaluated input or post-processing output (opt-in, sensitive) | Any system that returns the checked or rewritten text |
| `gen_ai.guardrail.security.content.input.hash` | Hash of the evaluated content for correlation without capture | Derived by the instrumentation |
| `gen_ai.guardrail.security.content.modified` | Whether the content actually changed | Guardrails AI fixed output, Bedrock masking |
| `gen_ai.guardrail.security.external_finding_id` | External finding record id | Services that return a finding id or emit to a SIEM |

## Capturability findings

Classifying each mapping by how directly the boundary yields it (`direct` when it
is readable at the boundary, `derivable` from library-owned semantics, `weak`
when it needs app-specific naming or an enum guess, `capture gap` when the
boundary cannot produce it) gives a consistent picture across systems:

- **Base attributes are `direct` or `derivable`.** Stage gives `target.type`; the
  result object gives `verdict.type`; the wrapper behavior gives `action.type`;
  the check name gives `component.name`. A generic instrumentation can set these
  without knowing anything security-specific.
- **Security overlay attributes are `weak` or a `capture gap`.** No surveyed
  in-process library labels a check as "security" or emits an OWASP category; that
  is derived per check. Policy identity, external finding ids, and modified
  content are exposed by some hosted services but not by in-process libraries.

This is the concrete evidence for the design: start from a generic guardrail
base that generic instrumentation can populate, and treat the security overlay as
an opt-in layer that a system populates only when it exposes that information.

## Gaps

- Several systems distinguish only allow versus deny. Richer verdict and action
  members (`modify`, `warn`, `escalate`) are demonstrated by systems that expose
  them (Bedrock, Azure, Guardrails AI), not by every system. This is multi-system
  coverage, not a defect.
- `gen_ai.guardrail.security.content.modified` and
  `gen_ai.guardrail.security.external_finding_id` are capture gaps for systems
  that block rather than rewrite and do not emit an external finding. They are
  left unset there rather than populated with a guessed value.
- Risk category is rarely a native field. It is derived from per-check knowledge,
  which is why it lives in the opt-in security overlay.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
