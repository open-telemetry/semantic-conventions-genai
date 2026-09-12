# Design choices behind usage metrics

This document explains the design of the token usage instruments defined in
[Semantic conventions for generative AI inference token usage metrics](/docs/gen-ai/gen-ai-inference-usage-metrics.md).

**Why is the modality breakdown on the counters and not on the histograms?
Why do we need two sets of metrics?**

Imagine a single histogram, `gen_ai.imaginary.inference.input_tokens`, with
modality as a dimension. Each inference operation would record one measurement
per modality in its input.

What could it answer?

- **Distribution of tokens per modality** - yes, if grouped by modality.
- **Total tokens per modality** - yes: the histogram's sum series does
  everything the counters do.
- **Distribution of input tokens per operation** - no. The p95 of the image
  parts plus the p95 of the text parts is not the p95 of an operation.

The problem is that the query for the third question looks valid:

```promql
histogram_quantile(0.95,
  sum(rate({"gen_ai.imaginary.inference.input_tokens"}[5m]))
)
```

Take a workload of 100 identical operations, each with 100 text and 200 image
input tokens. Every operation has an input of 300 tokens, but the histogram
holds 200 measurements, one hundred of `100` and one hundred of `200`:

| | Value |
| --- | --- |
| p95 the query returns | 200 |
| p95 of the actual input size | 300 |

The returned p95 of 200 is meaningless: no operation ever had that input size,
and it is lower than the smallest real input.

Modality could instead be part of the metric name:
`gen_ai.imaginary.inference.text.input_tokens` and so on. Each such histogram
records at most one measurement per operation.

This design is valid and hard to misuse, but one instrument per modality per
category multiplies quickly and histograms cost far more than counters. The
`gen_ai.client.inference.usage.detailed.input_tokens` and
`gen_ai.client.inference.usage.detailed.output_tokens` counters are broken down by
modality instead. They don't have the histogram usability problem and they
answer the common questions, cost approximation and the ratio between
modalities, at a much lower telemetry volume.

**Why does `gen_ai.token.modality` have an `unknown` value?**

So that summing a counter across `gen_ai.token.modality` always equals its
total, even against providers that report no modality breakdown.

The counters are aggregatable only because each token lands in exactly one
modality bucket, and `gen_ai.token.modality` is required on all of them. A
provider that reports no breakdown still has to put its tokens somewhere, and
without `unknown` both options are wrong: omitting the attribute makes the sum
inconsistent with providers that set it, and guessing `text` reports a modality
nobody observed.

`unknown` means "this producer had no modality information", not "this token had
no modality". It is the bucket that keeps the partition complete.

**Why are cached, cache-written, and reasoning tokens separate counters instead
of another attribute?**

We could report cache and reasoning tokens on the
`gen_ai.client.inference.usage.detailed.input_tokens` and
`gen_ai.client.inference.usage.detailed.output_tokens` counters instead, adding a
`gen_ai.token.cache` attribute with values `read`, `write`, and `uncached`, and
something similar for reasoning on the output side.

For each inference call we'd increment the input counter once per combination of
cache state and modality. If we sent 300 input tokens, 100 text and 200 image,
with 80 of the text tokens and all 200 image tokens served from cache, we'd
report

1. 80 with modality `text` and cache `read`
2. 20 with modality `text` and cache `uncached`
3. 200 with modality `image` and cache `read`

Every token lands in exactly one bucket, so these still produce correct
aggregations and rates however they are grouped.

The problem is that most providers don't give us that breakdown. For the call
above, OpenAI Chat Completions reports `text_tokens` and `image_tokens` next to
`cached_tokens` in `prompt_tokens_details`, and nothing says how the 280 cached
tokens split between text and image. 

Separate counters only carry the breakdown each provider actually reports:

- `gen_ai.client.inference.usage.detailed.input_tokens`: 100 `text`, 200 `image`
- `gen_ai.client.inference.usage.detailed.cache_read.input_tokens`: 280 `unknown`

The other reason is flexibility. Providers keep adding dimensions that apply to
one token category only. Anthropic splits cache writes by cache TTL, 5 minutes
or 1 hour, and prices the two differently. 
The `gen_ai.client.inference.usage.detailed.cache_write.input_tokens` instrument can
take a provider-specific TTL attribute later without touching anything else, and
summing over that attribute still gives the cache-write total. On a shared
counter the same attribute would appear on every input token, cached or not.
