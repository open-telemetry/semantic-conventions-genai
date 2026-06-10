# Changelog

## Unreleased

### 🛑 Breaking changes 🛑

- Change `gen_ai.request.top_k` type from `double` to `int` and scope it to
  decoding only. Retrieval spans now use the new
  `gen_ai.retrieval.top_k` attribute instead of `gen_ai.request.top_k`.
  ([#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217))
- Clarify `gen_ai.agent.id` stability expectations and scope; remove it from internal agent spans.
  ([#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242))

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
- Relax `gen_ai.provider.name` on `gen_ai.client.operation.duration` to `Conditionally Required`,
  to align with the `gen_ai.retrieval.client` and `gen_ai.memory.client` spans which already
  allow omitting `gen_ai.provider.name`.
  ([#214](https://github.com/open-telemetry/semantic-conventions-genai/pull/214))

### 📚 Clarifications 📚

- Clarify that when a provider reports both billed and consumed token counts
  (for example, Cohere), `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens` SHOULD report the billed counts.
  ([#211](https://github.com/open-telemetry/semantic-conventions-genai/pull/211))
- Generalize the `gen_ai.provider.name` description: remove inference-centric
  paragraphs, and add guidance for per-operation semantic conventions to
  clarify which kinds of providers apply when it is not clear from context.
  ([#212](https://github.com/open-telemetry/semantic-conventions-genai/pull/212))
- Clarify that a GenAI span SHOULD cover the duration of the operation
  as observed by the caller, including any retries.
  ([#216](https://github.com/open-telemetry/semantic-conventions-genai/pull/216))
- Clarify that `gen_ai.conversation.id` should only be populated from an available conversation identifier,
  and that instrumentations should not use fallback values such as generated UUIDs, trace IDs, or request-content hashes.
- Clarify that `gen_ai.request.top_k` is the top-K sampling/decoding parameter
  (e.g., Anthropic `top_k`, Cohere `k`) and not OpenAI's `top_logprobs`
  output-shaping parameter.
  ([#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217))
- Clarify MCP context propagation now that SEP-414 defines `traceparent`,
  `tracestate`, and `baggage` as unprefixed `params._meta` keys.
  ([#220](https://github.com/open-telemetry/semantic-conventions-genai/pull/220))
