# Changelog

## Unreleased

### 🛑 Breaking changes 🛑

- Restructure GenAI token usage attributes and metrics under a unified
  `gen_ai.token.*` namespace.
  - Renamed span attribute `gen_ai.usage.cache_creation.input_tokens` to
    `gen_ai.usage.cache_write.input_tokens` for symmetry with
    `gen_ai.usage.cache_read.input_tokens`.
  - Added per-modality span attributes
    `gen_ai.usage.{text,image,audio,video}.input_tokens` and
    `gen_ai.usage.{text,image,audio}.output_tokens`.
  - Added per-modality cache-read span attributes
    `gen_ai.usage.{text,image,audio,video}.cache_read.input_tokens` for
    providers that report per-modality cached-token breakdowns.
  - Replaced the `gen_ai.client.token.usage` histogram with counters
    `gen_ai.client.inference.tokens` (dimensioned by `gen_ai.token.type` and
    `gen_ai.token.modality`), `gen_ai.client.inference.input_tokens_by_cache`
    (dimensioned by `gen_ai.token.cache` and `gen_ai.token.modality`), and
    `gen_ai.client.inference.output_tokens_by_phase` (dimensioned by
    `gen_ai.token.phase`). Added opt-in histograms
    `gen_ai.client.inference.operation.{tokens,input_tokens,output_tokens}`.
  - Added new enum attributes `gen_ai.token.modality`
    (`text`/`image`/`audio`/`video`/`document`/`unknown`), `gen_ai.token.cache`
    (`uncached`/`read`/`write`), and `gen_ai.token.phase`
    (`response`/`reasoning`).

### 🚩 Deprecations 🚩

### 🚀 New components 🚀

### 💡 Enhancements 💡

- Add GenAI memory operation span and attributes for memory store lifecycle (create/delete),
  memory record create/update/upsert/search/delete operations, and record counts.
  ([#140](https://github.com/open-telemetry/semantic-conventions-genai/pull/140))
- Add `document` value to the `Modality` enum in the GenAI input/output/system-instructions
  message JSON schemas. Enables capturing PDF/DOCX (and similar) parts that today have to fall
  through to the free-form `string` branch of the modality `anyOf`.
- Mark `gen_ai.agent.name` as sampling-relevant on `create_agent`, `invoke_agent` client, and `invoke_agent` internal spans.
  ([#107](https://github.com/open-telemetry/semantic-conventions-genai/pull/107))
- Add `plan` operation for GenAI agent planning/task decomposition spans.
  ([#97](https://github.com/open-telemetry/semantic-conventions-genai/pull/97))
- Add `gen_ai.workflow.duration` metric to track duration of a workflow.
  ([#126](https://github.com/open-telemetry/semantic-conventions-genai/pull/126))
- Add `moonshot_ai` to `gen_ai.provider.name` well-known values.
  ([#99](https://github.com/open-telemetry/semantic-conventions-genai/pull/99))

### 🧰 Bug fixes 🧰

- Add missing `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` opt-in attributes to MCP server span.
  ([#136](https://github.com/open-telemetry/semantic-conventions-genai/pull/136))

### 📚 Clarifications 📚
