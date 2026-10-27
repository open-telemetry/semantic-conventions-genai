# Design choices behind token metrics

This document explains the design of the token instruments in
[Semantic conventions for generative AI inference token metrics](/docs/gen-ai/gen-ai-token-metrics.md).

## TL;DR

- **Histograms** (`gen_ai.client.inference.operation.*`) measure per-operation token size distributions. It is invalid to record more than one observation per operation that a histogram represents, so breakdowns like modality cannot go on the histogram without corrupting percentiles.
- **Counters** (`gen_ai.client.inference.usage.*`) measure cumulative token consumption over time for cost and spend tracking. They safely carry breakdowns like modality where each token bucket increments independently.

## Why is modality on counters instead of histograms? Why two sets of metrics?

Consider a single histogram, `gen_ai.imaginary.input_tokens`, with
modality as an attribute. Each operation records one measurement per modality.

What could that histogram answer?

- **Token distribution per modality.** Yes, when grouped by modality.
- **Total tokens per modality.** Yes. The histogram sum matches what counters record.
- **Input token distribution per operation.** No. Summing the p95 of text and the p95 of images does not give the p95 of an operation.

The query for that third question looks innocent enough:

```promql
histogram_quantile(0.95,
  sum(rate({"gen_ai.imaginary.input_tokens"}[5m]))
)
```

Take a workload of 100 identical operations, each with 100 text and 200 image
input tokens. Every operation consumed 300 tokens. But the histogram holds
200 measurements: one hundred 100s and one hundred 200s.

| | Value |
| --- | --- |
| p95 returned by the query | 200 |
| p95 of actual operation input size | 300 |

The returned p95 of 200 is nonsense. No operation had that size, and 200 is
lower than the smallest actual input.

We could put modality in the metric name instead:
`gen_ai.imaginary.text.input_tokens`. Each histogram would then record
at most one measurement per operation.

That works and prevents bad queries, but one instrument per modality and
category explodes quickly, and histograms are expensive. Instead, the
`gen_ai.client.inference.usage.input_tokens` and
`gen_ai.client.inference.usage.output_tokens` counters carry modality. They avoid
misleading quantiles, keep telemetry volume low, and answer the questions people
care about: usage rates, cost approximations, and ratios across modalities.

A histogram view does not combine a usage counter's modality contributions into
inference totals. An inference with 100 text tokens and 200 image tokens produces
two observations, 100 and 200, not one observation of 300. Dropping
`gen_ai.token.modality` does not combine them.

## Why record only positive contributions on usage counters?

Zeros do not affect consumption totals. To support per-modality statistics
across inferences, instrumentation would need to record a known count for each
modality being analyzed on every inference, including zeros. Otherwise, averages
and percentiles depend on which zero counts happen to be reported.

Providers may report only a total without a modality breakdown. Instrumentation
cannot fill missing modality counts with zeros.

Per-operation token histograms instead record one total per inference, using
zero when usage is missing.

## Why does `gen_ai.token.modality` have an `unknown` value?

Summing a counter across `gen_ai.token.modality` must equal the known total, even
for providers that report no modality breakdown.

The counters aggregate cleanly because each token lands in one modality bucket,
and `gen_ai.token.modality` is required on all of them. When a provider reports
no breakdown, instrumentation still has to put tokens somewhere. Without
`unknown`, both options fail: omitting the attribute breaks sums across
different providers, and guessing `text` invents data.

`unknown` means "the positive count is known but its modality cannot reliably be
determined", not "the count is unknown".

## Why are cached, cache-written, and reasoning tokens separate counters instead of attributes?

We could report cache and reasoning tokens on the main input and output counters
using a `gen_ai.token.cache` attribute (`read`, `write`, `uncached`), and
similar attributes for reasoning.

For each call, instrumentation would increment the counter for each combination
of cache state and modality. For 300 input tokens (100 text, 200 image) with
80 text and all 200 image tokens cached, it would record:

1. 80 tokens: `text`, `read`
2. 20 tokens: `text`, `uncached`
3. 200 tokens: `image`, `read`

Every token lands in one bucket, so aggregations and rates remain mathematically
sound.

The problem is that most providers do not report that breakdown. For that call,
OpenAI Chat Completions reports `text_tokens` and `image_tokens` alongside
`cached_tokens`, but never says how many cached tokens were text versus image.

Separate counters only carry the breakdown a provider actually reports:

- `gen_ai.client.inference.usage.input_tokens`: 100 `text`, 200 `image`
- `gen_ai.client.inference.usage.cache_read.input_tokens`: 280 `unknown`

Flexibility is the second reason. Providers regularly add dimensions that only
apply to one token category. Anthropic splits cache writes by TTL (5 minutes or
1 hour) with different pricing for each. The
`gen_ai.client.inference.usage.cache_write.input_tokens` counter can take a
provider-specific TTL attribute without touching other instruments, and summing
over TTL still yields the cache-write total. On a shared counter, that attribute
would leak onto every token.

## Why `usage` vs `operation` in the metric names?

The two metric families serve different purposes, reflected in their namespaces:

- `gen_ai.client.inference.usage.*` counters track cumulative token consumption
  over time. The `usage` namespace marks them as the instruments for measuring
  volume, spending rate, and cost.
- `gen_ai.client.inference.operation.*` histograms describe individual inference
  operations. The `operation` namespace indicates that each measurement represents
  a single operation's token count, producing per-operation distributions and
  percentiles rather than totals.

## Why do embeddings have only a histogram?

Embeddings responses report one input token count per request, with no output,
cached, or reasoning tokens.

So total embeddings usage comes from the sum of
[`gen_ai.client.embeddings.operation.input_tokens`](/docs/gen-ai/client-embeddings.md#metric-gen_aiclientembeddingsoperationinput_tokens).

Detailed usage for embeddings may be added later, see
[#577](https://github.com/open-telemetry/semantic-conventions-genai/issues/577).
