# Changelog

## Unreleased

### 🛑 Breaking changes 🛑

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
