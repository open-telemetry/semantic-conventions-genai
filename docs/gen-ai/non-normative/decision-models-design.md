# Decision-model inference: issue #580 investigation

Design rationale for the first implementation. This document is non-normative.
Provider documentation and SDK source were inspected on 2026-10-12.
Repository baseline: `6fd0d763a092db245a54104fc1124031eb3c51d2`.
Related issue: [#580](https://github.com/open-telemetry/semantic-conventions-genai/issues/580).

This changeset adds `decision` to `gen_ai.operation.name` and attaches its recording
guidance to the existing inference span. Existing inference metrics carry the same
operation value. The OpenAI reference uses a real SDK with HTTP mock responses to
demonstrate routing, scoring, partial refusal, and errors.

This first slice supports filtering decision inference latency, usage, and failures.
It does not standardize result content or claim to resolve all of #580. Results
need a mapping for multiple answers, typed choices, and individual refusals.

## Current architecture

The source of truth is [the YAML model](../../../model/gen-ai/). Provider-independent
attributes live in `registry.yaml`. The `gen_ai.client.inference` definition in
`spans.yaml` attaches them through individual `ref` entries and shared `ref_group`
entries, assigning requirement levels at the signal. Provider extensions add
their own attributes to the shared span. Registry membership alone does not
attach an attribute to a signal.

An inference span represents one logical SDK operation, including automatic
retries. Its usual name is `{gen_ai.operation.name} {gen_ai.request.model}` and
its kind is `CLIENT`, with an in-process `INTERNAL` allowance. The existing
operation values include `chat`, `generate_content`, and `text_completion`.
Span type and operation value are separate concepts: a new operation value
does not require a new span type or duration metric.

`gen_ai.client.inference.duration` measures the same operation boundary.
Inference token histograms describe per-operation usage; token counters describe
cumulative usage. Record usage once per SDK call, not once per returned question.
Only record values reported by the provider or obtainable through the existing
usage rules. Missing usage is not zero, and zero output tokens is not an error.

The [content guidance](../gen-ai-spans.md#capturing-instructions-inputs-and-outputs)
makes input/output capture opt-in. `gen_ai.client.inference.operation.details`
can carry the inference attributes independently from traces. Its current model
uses event attributes; an arbitrary event body is not an established decision
result schema.

The [reference rules](../../../reference/CONTRIBUTING.md) require an actual library
boundary and values readable from parameters the library interprets, returned
objects, exceptions, or library state. Mock service responses may exercise a real
SDK, but application-defined metadata and invented response fields cannot justify
a convention. Implementations need runnable scenarios under
`reference/scenarios/<library>/`, conformance configuration, locked dependencies,
and regenerated `data.json` and reports.

Existing patterns favor reuse where the operation and data have the same meaning.
They also define specialized operations for distinct observable library calls.
[Issue #249](https://github.com/open-telemetry/semantic-conventions-genai/issues/249)
discusses grouping operations into shared span/metric definitions; it is a proposal,
not a requirement to create one span type per endpoint.

### Existing fields and their limits

| Existing convention | Reusable meaning | Boundary for decisions |
| --- | --- | --- |
| `gen_ai.provider.name`, request/response model, server address | Provider, requested model, returned model, endpoint. | No new decision identity fields needed. |
| Inference duration and `gen_ai.usage.*` | Latency and token usage. | Keep at request scope; do not duplicate for each answer. |
| `error.type`, span status, exception event | SDK or request failure. | An uncertain or refused answer is not automatically a failed request. |
| `gen_ai.request.choice.count` | Number of alternative completions requested. | Neither number of decision options nor number of questions. |
| `gen_ai.output.type` | Requested content format. | A JSON HTTP response does not imply a requested JSON generation format; it does not identify predicate/choice/score. |
| `gen_ai.output.messages` | Captured generated messages. | Custom parts are schema-valid, but multiple decision answers are not automatically alternative generations. A portable mapping is missing. |
| `gen_ai.response.finish_reasons` | Why each generation stopped. | No documented decision mapping; do not manufacture `stop`, `error`, or `content_filter` from answer types. |
| `gen_ai.evaluation.result` and `gen_ai.evaluation.score.*` | Evaluation of GenAI output. | Not every routing or scoring request evaluates GenAI output. Do not relabel all decisions as evaluations. |
| `gen_ai.prompt.name`, `gen_ai.prompt.version` | An observable named/versioned prompt template. | Arbitrary question names are not prompt or rubric versions. |
| `gen_ai.response.id` | Provider response identifier. | Neither inspected direct decision response schema defines an ID; do not substitute a question name. |

`GenericPart` in [models.py](models.py) permits custom content parts. This provides
an extension point, not an agreed interpretation of a decision answer. Ordinary
chat or Responses calls that happen to return application-defined routing JSON
can retain their existing operation and opt-in message capture. Instrumentation
cannot infer a dedicated decision API merely by parsing that JSON.

### Related work and scope

- [PR #535](https://github.com/open-telemetry/semantic-conventions-genai/pull/535)
  proposes pre-execution tool approval decisions. It concerns whether a proposed
  tool call may execute, not the model inference that might inform that policy.
- [PR #427](https://github.com/open-telemetry/semantic-conventions-genai/pull/427)
  proposes guardrail operations and distinguishes a verdict from caller enforcement.
  It remains separate from the decision-model call used inside a guardrail.
- [Issue #33](https://github.com/open-telemetry/semantic-conventions-genai/issues/33)
  and closed [PR #185](https://github.com/open-telemetry/semantic-conventions-genai/pull/185)
  discuss evaluation spans. The latter records unresolved operation/result
  association questions; it does not establish an evaluation operation here.
- [PR #359](https://github.com/open-telemetry/semantic-conventions-genai/pull/359)
  addresses evaluator provenance. It does not make scores comparable across rubrics.

The inspected decision-related PR search did not identify another implementation of
#580. Open proposals above are prior art, not adopted conventions.

## Provider evidence

| Provider/API | Decision types and inputs | Returned result | Probability/confidence | Abstention/refusal |
| --- | --- | --- | --- | --- |
| OpenAI `POST /v1/decisions` | Shared `input`; ordered `questions`; `predicate`, `choice`, `score`. | Ordered `answers`; optional question names; typed choice or numeric score. | Predicate probability; distributions and a separate confidence for choice/score. | Per-answer `type="refusal"`; other answers may succeed. No dedicated abstention found. |
| TypeSafe Jev `POST /v1/systemone` | Shared `state`; named question map; `noul`, `choice`, `score`. | Answer map; string choice; numeric score with `legend`. | Noul probability; distributions and derived confidence for choice/score. | No refusal/abstention variant in inspected answer types. Low-confidence fallback is caller behavior. |
| Cloudflare Clef Workers AI | `state` and named `noul`, `choice`, `score` questions. | Answer map; routing choice and weighted level score. | Per-option probabilities documented. Exact confidence contract not established in the inspected page. | Unknown from inspected page. |

Sources: [OpenAI API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create),
[TypeSafe HTTP reference](https://docs.typesafe.ai/api),
[Cloudflare Clef](https://developers.cloudflare.com/workers-ai/models/clef/).
Unknown means unverified, not unsupported. These are documentation/source findings,
not observations from production calls. Cloudflare corroborates breadth but was
not used to infer missing fields from another provider's contract.

The [OpenAI guide](https://developers.openai.com/api/docs/guides/decisions) describes
scores as expected zero-based level indices. Its confidence field is separate
from the distribution; the inspected guide does not establish a formula that can
be equated with another provider's confidence. A predicate probability estimates
truth, without returning a thresholded yes/no action.

[TypeSafe confidence](https://docs.typesafe.ai/confidence) is a distribution statistic.
Choice confidence depends on the highest probability and option count; score
confidence additionally considers distances between ordered levels. Neither is
simply the selected probability. Noul has no separate returned confidence.
Caller-computed thresholds, recalibration, and a model-generated self-assessment
are distinct from these provider fields. Calibration claims alone do not create
a common measurable contract.

[TypeSafe Score](https://docs.typesafe.ai/primitives/score) uses ordered criteria
and may produce a value between levels. A score needs its level meanings and
direction to be interpretable. A bounded number is not inherently relevance,
risk, a probability, or a universal quality metric.

### SDK mapping and remaining capabilities

The [OpenAI SDK response types](https://github.com/openai/openai-python/blob/main/src/openai/types/decision.py)
preserve string and boolean choice values separately. The response has `model`,
`answers`, and `usage`, with no decision ID or explanation field. Refusal identifies
the affected question but does not carry a reason establishing a safety category.
Do not turn it into a safety refusal classification without further evidence.

The [TypeSafe public response types](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_core/response_types.py)
expose `answers`, `model`, and usage with optional token counts. Its SDK converts
score map keys to integers. It skips unknown future answer types, so a missing
answer cannot safely be interpreted as abstention.
The [generated wire types](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_schemas/models.py)
provide no dedicated refusal, explanation, rubric-version, or response-ID field.

Both direct APIs accept caller-defined choice sets. Neither is a winner-only
API for choice results: both return a distribution as well. The inspected
contracts do not establish a general free-form bounded numeric judgment separate
from the ordered-level score. Instructions and level descriptions are rubric
content; they do not supply stable rubric identity or versioning.

## Scenario matrix, before choosing fields

Illustrative values below describe consumer needs, not captured provider responses.

| Scenario | Inputs | Output | Telemetry consumer needs | Evidence and limit |
| --- | --- | --- | --- | --- |
| Binary predicate | Evidence plus yes/no question. | Probability, e.g. 0.87. | Debug threshold crossings. | OpenAI predicate / Jev Noul; neither supplies the application's yes/no action. |
| Binary choice with certainty | Two explicit choices. | Choice plus distribution and confidence. | Inspect selected label and its probability. | Both direct APIs; probability and confidence differ. |
| Multi-choice routing | Request plus billing/technical/sales options. | Selected option. | Explain model routing recommendation. | Both APIs; caller may route elsewhere. |
| Multi-choice distribution | Same candidate set. | Probability for each option. | Analyze ambiguity and calibration against later ground truth. | Both APIs; full content may be sensitive and large. |
| Bounded score | Evidence and ordered relevance levels. | Expected index, e.g. 0.84 on two levels. | Compare judgments within one known rubric. | Both APIs; different scales and questions are not interchangeable. |
| Abstention | Caller threshold or explicit uncertain option. | Fallback action or ordinary selected option. | Explain deferred action. | No dedicated direct-API abstention established; inference instrumentation cannot observe downstream enforcement. |
| Refusal | One or several questions. | Refusal for one answer. | Distinguish unanswered questions from failures. | OpenAI explicit variant; preserve partial success. |
| Error | Request. | SDK exception / unsuccessful request. | Reliability and latency analysis. | Existing error conventions; no synthesized answer. |
| Repeated/versioned rubric | Application-managed rubric v2. | Score. | Reproduce or compare identical configurations. | Native rubric version unknown; do not invent one from question names. |
| Mixed questions | One input, predicate + choice + score. | Several typed answers. | Associate each result with its question. | Both APIs; scalar span result attributes lose this relationship. |

## Compare semantic models

| Option | Fit with the repository | Benefit | Problem | Recommendation |
| --- | --- | --- | --- | --- |
| A: existing inference operation plus decision attributes. | Reuses the inference signal. | Minimal operational change. | `chat`/`text_completion` describe different API contracts; classifying from prompt intent is not generically instrumentable. | Retain for actual chat/Responses APIs, not dedicated decision endpoints. |
| B: `decision` operation within `gen_ai.client.inference`. | Same separation of span type and operation used today. | Portable filtering for latency, failures, and usage. | Needs explicit endpoint mapping and a separate answer representation. | Implemented for operation telemetry; result representation deferred. |
| C: result event associated with inference. | Similar correlation mechanism to existing result/detail events. | Can preserve per-answer identity, content, and partial refusal. | New event/schema and correlation rules; risk of duplicating the inference detail event. | Evaluate against typed content parts before adding a new event. |

Options B and C are not mutually exclusive. One concerns the operation, the other
its results. A separate decision span type, separate duration metric, or one span
per answer has no demonstrated need in this first slice. One request containing
ten answers still has one request duration and one usage total.

## Operation and deferred candidate fields

Only the `decision` operation value is implemented. All other names in this table
are discussion placeholders. Per-answer fields need a result schema or signal first.
For those fields, the requirement column describes a possible future treatment.

| Candidate | Purpose / example | Type and possible requirement | Cardinality / privacy | Evidence and existing-field gap | Disposition |
| --- | --- | --- | --- | --- | --- |
| `gen_ai.operation.name=decision` | Separate decision inference traffic. | Existing string; required on inference. | One low-cardinality value; no content. | Dedicated endpoints across providers; existing generation values do not identify their contract. | Implemented on inference spans and metrics. |
| `gen_ai.decision.type` | Interpret an answer, e.g. `predicate`. | String enum per answer; required within a future typed result. | Few values; little direct content risk. | OpenAI predicate maps conceptually to Jev Noul; no current typed decision result. | No scalar span field; settle normalization. |
| `gen_ai.decision.outcome` | Inspect route, e.g. `technical`. | String or boolean per answer; opt-in. | Potentially unbounded and sensitive. | Both return `choice`; OpenAI preserves booleans. Messages capture content but lack a portable choice field. | Consider typed content, not a string-only scalar. |
| Selected probability | Inspect ambiguity of selected choice, e.g. 0.72. | Double per answer; opt-in if reported. | Continuous values; can disclose sensitive inference. | Read distribution entry matching the selected typed value; no matching current field. | Candidate content field; never substitute confidence. |
| Predicate probability | Inspect truth estimate, e.g. 0.87. | Double per answer; opt-in. | Continuous values and sensitive judgments. | OpenAI `probability`, Jev `noul`; not a selected-action probability. | Keep distinct from selected probability. |
| `gen_ai.decision.score` | Compare judgments under one rubric, e.g. 1.1. | Double per answer; opt-in with scale context. | Continuous values; potentially sensitive assessment. | Both score APIs; evaluation score applies only in an evaluation context. | Defer until scale/result mapping is specified. |
| `gen_ai.decision.confidence` | Explain certainty gating, e.g. 0.55. | Double; no portable requirement proposed. | Continuous values; sensitive assessment. | Returned by both; TypeSafe defines type-dependent statistics, equivalence to OpenAI unknown. | Reject generic comparable confidence. |
| `gen_ai.decision.candidates` | Reconstruct allowed alternatives. | Structured list/map; opt-in only if a content schema is accepted. | Unbounded labels/descriptions, size, PII. | Both request choice sets; completion count is unrelated. | Reject as default span attributes. |
| Candidate count | Diagnose size of selection task, e.g. 3. | Integer per choice question; optional if eventually justified. | Lower privacy/size risk; numeric range can still vary. | Length of SDK choices/criteria; `gen_ai.request.choice.count` is not this count. | Defer: insufficient added consumer value for first slice. |
| Full probabilities | Diagnose alternatives and calibration. | Structured per-answer distribution; opt-in. | Candidate-dependent size and sensitive labels. | Both APIs return it; no existing portable schema. | Consider bounded/redacted content; never metric dimensions. |
| `gen_ai.decision.abstained` | Explain fallback. | Boolean; no requirement proposed. | Low cardinality; policy meaning can be sensitive. | No native field established; caller thresholds are outside model SDK. | Reject inferred attribute. |
| Refusal result | Distinguish an unanswered question. | Typed per-answer variant; only when explicitly returned. | Low type cardinality; question association may be sensitive. | OpenAI refusal; token finish reasons do not define this mapping. | Result-level candidate, not a call-wide error flag. |
| `gen_ai.decision.rubric.*` | Reproduce score interpretation. | Text/structured levels opt-in; ID/version unspecified. | Rubric text and caller identifiers can be sensitive/unbounded. | Level definitions exist; native rubric IDs/versions unverified. | Keep text in controlled content; no ID/version attributes. |
| Question identity | Join each answer to its question. | Index or name in future result; name opt-in. | Index bounded per request; names may contain user data. | OpenAI ordered answers/name, Jev map key. No current decision correlation field. | Resolve before choosing an event or message mapping. |

None of the candidate result values should become metric dimensions. Selected
probability is smaller than a distribution but cannot support full multiclass
calibration analysis. Candidate count is safer than candidate content but cannot
explain which options were available. These are explicit information tradeoffs.

Scores should retain their original scale, level order, and interpretation in
controlled content or externally managed configuration. Minimum and maximum alone
do not identify a rubric. Avoid rescaling all scores to 0..1 or hashing arbitrary
rubric text into a supposed provider identifier.

## Reference implementation and result scenario plans

The runnable [OpenAI decision scenario](../../../reference/scenarios/openai/decisions.py)
uses SDK 3.26.0, the first release with standalone Decisions support. Its HTTP
transport asserts the serialized request, then returns synthetic predictions in
the documented response schema. Instrumentation reads the resulting SDK objects.
Unit tests check refusal versus error, request-scoped usage, and content omission.
This proves SDK capturability, not live-service behavior or model accuracy.

Below are sketches of the result fields a future result convention could use.
The TypeSafe sketch has not been executed; OpenAI operation coverage is implemented
in the linked scenario. Neither sketch establishes a portable result schema.

### Routing: TypeSafe Python SDK

```python
from typesafe_sdk import Choice, TypeSafeClient

def routing_call(client: TypeSafeClient):
    return client.system_one(
        model="jev-latest",
        state="Checkout returns an error whenever I submit my order.",
        questions={
            "department": Choice(
                instructions="Which team should handle this request?",
                criteria={
                    "billing": "Invoices and payments",
                    "technical": "Errors and configuration",
                    "sales": "Plans and upgrades",
                },
            ),
        },
    )
```

This call shape is supported by the
[official synchronous client](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_core/client/sync/client.py).
Wrap exactly `system_one`, after client setup. Model/provider identity and
elapsed time belong to the enclosing inference span. Read usage from
`response.usage` and omit missing counts. Obtain the selected route from
`response.answers["department"].choice`, and its probability from the matching
`probabilities` entry. Confidence remains a separate provider value.

The selected route needs the future opt-in result representation. Do not emit
an application routing action or abstention merely because confidence is low.
Use an SDK exception for a request-failure variant. No observed refusal variant
is available to this plan. A real endpoint returning `technical` is possible,
not an assertion that the example must yield it.

### Bounded relevance score: OpenAI Python SDK

```python
from openai import OpenAI

def relevance_call(client: OpenAI):
    return client.decisions.create(
        model="gpt-6-luna",
        input="Query: reset a password. Passage: choose Forgot password to reset it.",
        questions=[
            {
                "type": "score",
                "name": "relevance",
                "instructions": "How useful is the passage for answering the query?",
                "levels": [
                    {"label": "irrelevant", "description": "Does not address the query."},
                    {"label": "relevant", "description": "Directly addresses the query."},
                ],
            },
        ],
    )
```

The [official Decisions resource](https://github.com/openai/openai-python/blob/main/src/openai/resources/decisions.py)
defines this SDK boundary. The implemented scenario reads the result type before reading
`score`; `refusal` is an alternative answer. For a score, retain its two ordered
levels so a value between 0 and 1 remains interpretable. This is a weighted level
index for this question, not a general probability that retrieval succeeded.

Read returned model and usage at call scope. Test a separate multi-question request
to prove that one refusal does not discard successful answers or duplicate usage.
Do not populate `gen_ai.evaluation.*` solely because the question is named
`relevance`: this call evaluates a retrieved passage, not necessarily GenAI output.

### Acceptance checks before adding result conventions

1. Extend the pinned OpenAI coverage to TypeSafe and run both through real SDK
   serialization and response parsing. Use provider-documented mock response
   shapes or explicitly authorized live calls; never assert invented fields.
2. Compare both providers' routing and score projections. Preserve boolean versus
   string choices, mixed answer types, optional names, and original score scales.
3. Exercise refusal, transport failure, missing usage, zero usage, and unknown
   answer types where the SDK supports them. Do not turn missing data into a
   result or a zero value.
4. Verify one inference span and one duration/usage observation per logical call.
   Content disabled should omit choices, rubrics, distributions, and question names.
5. Choose the result signal/schema, then bind every new attribute to it. Update
   scenario README status, conformance declarations, data, and reports together.

## Maintainer decisions

1. Should dedicated typed-decision endpoints share `gen_ai.client.inference` with
   a new `decision` operation, or is a different operation spelling preferred?
2. Should each answer be a typed content part in the existing inference detail
   surface, or an independently correlated result event? How does either mapping
   preserve the one-generation/one-message rule?
3. Can the first result slice cover choice and explicit refusal while retaining
   string/boolean values, leaving score and confidence for later work?
4. Is the implemented operation-only slice sufficient initial consumer value,
   or should result mapping be settled before adopting the operation?

## Validation and compatibility

The new operation value extends the inference span and existing metric dimensions.
No attributes, namespaces, span types, result schemas, or metrics are added.
The OpenAI scenario dependency is upgraded from 3.22.0 to 3.26.0 for Decisions
support. A Towncrier enhancement fragment records the consumer-visible addition.

The workflow in [CONTRIBUTING.md](../../../CONTRIBUTING.md) and
[Makefile](../../../Makefile) uses `make generate-all` and `make check-policies`.
Policy checking performs Weaver model checks and shared policies, including local
JSON-schema annotation policy. JSON schemas are generated from `models.py` as
part of `generate-all`; generated files must not be edited by hand.

Run `uv run run-scenario openai` from `reference/`, then `uv run update-reports`,
`make generate-all`, and `make check-policies`. Focused tests run with
`uv run --project reference/scenarios/openai python -m unittest discover -s reference/scenarios/openai -p test_decisions.py -v`
from the repository root. The runner checks the working tree model and warns about
violations by default; use `--strict` when assessing unresolved conformance gaps.

## Suggested issue comment

I compared the OpenAI Decisions API, TypeSafe Jev, and Cloudflare Clef. Their
shared boundary appears to be one inference call with several typed questions,
so I suggest exploring a `decision` operation under the existing inference span
and reusing duration, usage, provider/model, and error conventions. A local first
implementation adds that operation with an OpenAI SDK reference and telemetry tests.

Result modeling needs a separate decision: each answer needs correlation, choices
can be typed, and OpenAI can refuse individual answers. I would keep confidence,
full distributions, and rubric text out of default span attributes. Would the SIG
prefer an operation-only first change, or a choice/refusal result slice using
typed content parts versus a result event? Result attributes are deliberately
deferred in the current implementation.

## Suggested PR title

Add decision inference operation with OpenAI reference coverage

## Suggested PR description

### Description

Add `decision` as an inference operation so dedicated decision APIs can be filtered
in latency, usage, and failure telemetry. This is a first slice of #580; per-question
result attributes remain deferred.

### Motivation

Operators need to distinguish decision inference traffic and explain model routing
recommendations. [OpenAI Decisions](https://developers.openai.com/api/docs/guides/decisions),
[TypeSafe Jev](https://docs.typesafe.ai/api), and
[Cloudflare Clef](https://developers.cloudflare.com/workers-ai/models/clef/) provide
prior art for typed questions. Per-answer correlation and confidence semantics
need a deliberate mapping before telemetry fields are standardized.

### Prototype

The OpenAI reference exercises the real Decisions SDK through an HTTP mock for
routing, scoring, partial refusal, and request errors. Tests verify that multiple
answers do not multiply usage and that refusal does not become a request failure.
The design note maps TypeSafe and Cloudflare prior art and explains deferred results.

### Checklist

- [x] Motivation section filled in above.
- [x] OpenAI reference scenarios updated; TypeSafe remains a documented mapping.
- [x] Towncrier enhancement fragment added.
