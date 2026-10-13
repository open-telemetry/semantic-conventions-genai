# Decision-model inference: issue #580 investigation

Design rationale for the first implementation. This document is non-normative.
Provider documentation and SDK source were inspected on 2026-10-12.
The result mapping was rechecked on 2026-10-13.
Repository baseline: `6fd0d763a092db245a54104fc1124031eb3c51d2`.
Related issue: [#580](https://github.com/open-telemetry/semantic-conventions-genai/issues/580).

This changeset adds `decision` to `gen_ai.operation.name` and attaches its recording
guidance to the existing inference span. Existing inference metrics carry the same
operation value. Opt-in `gen_ai.decision.results` captures correlated predicate,
choice, score, and refusal results on that span or the existing inference-detail
event. The OpenAI reference emits these results through real SDK calls with HTTP
mock responses.

Result content is disabled by default. Generic confidence, inferred abstention,
complete candidate lists, full distributions, and arbitrary rubric text remain
excluded for the reasons below. This design covers the observed result contracts;
it does not claim that all future decision APIs share them.

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
uses event attributes. The new result attribute is inherited from the inference
span; it does not require a separate event or arbitrary event body.

Repository [reference rules](../../../reference/CONTRIBUTING.md) require an actual library
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
| `gen_ai.output.messages` | Captured generated messages. | Multiple decision answers are not alternative generations; the new structured result attribute avoids inventing message roles or generations. |
| `gen_ai.response.finish_reasons` | Why each generation stopped. | No documented decision mapping; do not manufacture `stop`, `error`, or `content_filter` from answer types. |
| `gen_ai.evaluation.result` and `gen_ai.evaluation.score.*` | Evaluation of GenAI output. | Not every routing or scoring request evaluates GenAI output. Do not relabel all decisions as evaluations. |
| `gen_ai.prompt.name`, `gen_ai.prompt.version` | An observable named/versioned prompt template. | Arbitrary question names are not prompt or rubric versions. |
| `gen_ai.response.id` | Provider response identifier. | Neither inspected direct decision response schema defines an ID; do not substitute a question name. |

`GenericPart` in [models.py](models.py) permits custom content parts. This provides
an extension point, but no question correlation or typed result contract. Ordinary
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
| B: `decision` operation within `gen_ai.client.inference`. | Same separation of span type and operation used today. | Portable filtering for latency, failures, and usage. | Needs explicit endpoint mapping and an answer representation. | Implemented with a structured per-question result attribute. |
| C: result event associated with inference. | Existing inference-detail event inherits inference attributes. | Can preserve per-answer identity, content, and partial refusal. | A dedicated new event would duplicate this surface. | Reuse the inference-detail event with the same structured results; no new event. |

Options B and C are not mutually exclusive. One concerns the operation, the other
its results. A separate decision span type, separate duration metric, or one span
per answer has no demonstrated need in this first slice. One request containing
ten answers still has one request duration and one usage total.

## Implemented semantic model and field rationale

`gen_ai.operation.name=decision` identifies dedicated typed-decision APIs. It remains
a required, low-cardinality string on inference. The new `gen_ai.decision.results`
attribute is an opt-in structured array, attached to the inference span and inherited
by the existing inference-detail event. JSON Schema defines four disjoint result
variants; there is no permissive generic-message fallback. It is never a metric
dimension. JSON serialization on spans follows the existing content convention.

The array is needed because scalar attributes lose per-question association and
partial refusal. Existing generated-message conventions require one generation per
message, which does not describe these answers. Evaluation results concern evaluation
of GenAI output, while these APIs also classify arbitrary input.

| Field within each result | Purpose / example | Type and requirement | Cardinality / privacy | Runtime evidence and existing-field gap |
| --- | --- | --- | --- | --- |
| `question_index` | Associate an answer with its original request question, e.g. 1. | Nonnegative integer, required. | Request-local index; no prompt content. | OpenAI positional order; Jev request-map iteration order plus returned key. No existing decision correlation field. |
| `question_name` | Identify the question to the consumer, e.g. `department`. | String, optional when available. | Arbitrary and potentially sensitive; captured only with results. | OpenAI answer name and Jev map key. Neither a response ID nor a rubric version. |
| `type` | Interpret the answer: predicate, choice, score, refusal. | String discriminator, required. | Four values; refusal still discloses an inference result. | OpenAI answer variants; Jev `noul` maps to predicate. Generation finish reasons cannot represent partial refusal. |
| `value` for choice | Inspect the recommended route, e.g. `technical`. | String or boolean, required for choice. | Unbounded values; sensitive classifications. | OpenAI typed `choice` and Jev string `choice`. Existing completion counts and output modality do not describe selected options. |
| `probability` for choice | Inspect ambiguity of the selected option, e.g. 0.72. | Number in [0, 1], optional when reported. | Continuous and sensitive; content only. | Read the distribution entry for the exact typed selected value. Neither generic confidence nor a calibrated certainty claim. |
| `probability` for predicate | Interpret truth estimate, e.g. 0.87. | Number in [0, 1], required for predicate. | Continuous and sensitive; content only. | OpenAI `probability`, Jev `noul`. Does not imply a thresholded yes/no action. |
| `value` for score | Compare a judgment within its rubric, e.g. 1.68. | Number, required for score. | Continuous and potentially sensitive. | Both APIs report expected level index; evaluation score has a different scope. Preserve the original index scale. |
| `levels` for score | Interpret score scale, e.g. `["irrelevant", "partial", "relevant"]`. | Ordered string array, required for score, at least two labels. | Variable-size, sensitive labels; omit the result if the complete scale cannot be captured. | OpenAI request labels; Jev string-valued legend sorted by contiguous zero-based indices. Min/max alone do not explain level meanings. |

Refusal has only correlation fields and its type. An API must explicitly return it;
low confidence, a missing answer, and a request error do not imply refusal.
The score variant covers expected zero-based level indices only. It does not assign
meaning to arbitrary numeric outputs or providers' other scoring contracts.
Consumers must use application-managed rubric context when comparing results across
requests: identical labels do not prove identical instructions or rubric versions.

### Alternatives intentionally excluded

- Full candidate lists and distributions: they expose every label and grow with
  candidate count. Selected value and selected probability support routing diagnosis
  with less content, though they cannot support full multiclass calibration analysis.
- Candidate count: smaller and safer than labels, but insufficient added consumer
  value for this change. `gen_ai.request.choice.count` remains completion count.
- Generic confidence: TypeSafe defines distribution statistics whose interpretation
  varies by question type. Equivalence to OpenAI confidence is not established.
- Inferred abstention: no native direct-API abstention variant was found. Application
  thresholds and fallback actions remain outside the model operation.
- Arbitrary rubric text and rubric IDs/versions: instructions and descriptions are
  sensitive content; a portable native rubric identity/version is unverified. Score
  labels preserve the numeric scale without claiming to reproduce the full rubric.
- A new result event or one span per answer: existing inference-detail events carry
  the same result attribute with trace correlation. Usage and latency stay per call.

## Reference implementation and provider mappings

The runnable [OpenAI decision scenario](../../../reference/scenarios/openai/decisions.py)
uses SDK 3.26.0, the first release with standalone Decisions support. Its HTTP
transport asserts the serialized request, then returns synthetic predictions in
the documented response schema. Instrumentation reads the resulting SDK objects.
Unit tests inspect exported results, trace-correlated structured events, privacy
defaults, original score scales, typed choices, and refusal versus error.
This proves SDK capturability, not live-service behavior or model accuracy.

Below are provider call shapes supporting the mapping. The TypeSafe sketch has not
been executed; OpenAI operation and result capture are implemented in the linked
scenario. TypeSafe mapping is based on its official API and SDK contracts.

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

The selected route maps to a choice result's `value` and `probability`. Do not emit
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
`score`; `refusal` is an alternative answer. For a score, the emitted result retains its two ordered
labels so a value between 0 and 1 remains interpretable. This is a weighted level
index for this question, not a general probability that retrieval succeeded.

Returned model and usage stay at call scope. A separate multi-question test verifies
that one refusal does not discard successful answers or duplicate usage.
Do not populate `gen_ai.evaluation.*` solely because the question is named
`relevance`: this call evaluates a retrieved passage, not necessarily GenAI output.

### Result validation

The reference exercises all four schema variants through SDK serialization and
response parsing. Tests verify explicit opt-in, boolean/string choice separation,
scores above one on a three-level scale, omitted unknown answers without index
renumbering, event trace correlation, and exclusion of results from metric labels.
Missing answers and HTTP errors produce no fabricated result. Malformed-input
defensive tests are labeled separately from valid provider contract examples.

The generated JSON Schema enforces variant fields, scalar types, probability bounds,
and scale presence. Its companion Python model additionally checks score bounds
that depend on the number of levels and uniqueness of question indices. Those
cross-field constraints cannot be expressed by this JSON Schema alone.
Tests validate actual exported content against the generated JSON Schema and check
it matches the Python source. This is necessary because the pinned conformance
runner's content policy uses a fixed list of schemas that excludes this new one.

## Maintainer decisions

1. Is one structured result attribute on inference spans and detail events the
   preferred surface for typed decisions, given the generation-message invariant?
2. Is the expected-index score contract sufficiently narrow, including omission
   when a complete ordered string scale cannot be captured?
3. Should cross-provider confidence or full distributions be considered separately
   after a comparable interpretation and content-size controls are established?

## Validation and compatibility

The operation value extends inference and existing metric dimensions. One new
structured attribute and JSON schema carry results on inference spans and detail
events. No span type, event type, or metric is added. Existing generation schemas
are unchanged; the new result schema does not inherit their generic-part fallback.
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

The local implementation adds a `decision` inference operation and one opt-in
structured `gen_ai.decision.results` attribute on inference spans and existing
detail events. Results retain question correlation, typed choices, selected
probabilities, score scales, and explicit per-question refusals. OpenAI SDK
reference scenarios emit all four variants, with tests for privacy defaults,
partial refusal, usage accounting, and structured event correlation.

Both OpenAI and TypeSafe contracts support these mappings. Generic confidence, full
distributions, inferred abstention, and rubric identities remain excluded. Does
the SIG prefer this structured result surface, and is the expected-index score
contract appropriately scoped?

## Suggested PR title

Add decision inference and per-question results with OpenAI reference coverage

## Suggested PR description

### Description

Add `decision` as an inference operation so dedicated decision APIs can be filtered
in latency, usage, and failure telemetry. Add opt-in per-question predicate, choice,
score, and refusal results on inference spans or existing detail events.
Results preserve correlation, typed choices,
selected probabilities, and ordered score scales.

### Motivation

Operators need to distinguish decision inference traffic and explain model routing
recommendations. [OpenAI Decisions](https://developers.openai.com/api/docs/guides/decisions),
[TypeSafe Jev](https://docs.typesafe.ai/api), and
[Cloudflare Clef](https://developers.cloudflare.com/workers-ai/models/clef/) provide
prior art for typed questions. Per-answer correlation is addressed through typed
results; generic confidence remains
excluded because its cross-provider meaning is not established.

### Prototype

The OpenAI reference exercises the real Decisions SDK through an HTTP mock for
routing, scoring, partial refusal, and request errors. Tests verify that multiple
answers do not multiply usage and that refusal does not become a request failure.
The design note maps TypeSafe and Cloudflare prior art and explains the result
schema, privacy controls, and excluded confidence/distribution fields.

### Checklist

- [x] Motivation section filled in above.
- [x] OpenAI reference scenarios updated; TypeSafe remains a documented mapping.
- [x] Towncrier enhancement fragment added.
