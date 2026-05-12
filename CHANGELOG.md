# Changelog

## Unreleased

### 🛑 Breaking changes 🛑

### 🚩 Deprecations 🚩

### 🚀 New components 🚀

### 💡 Enhancements 💡

- Add GenAI memory operation spans and attributes for memory store lifecycle (create/delete),
  memory record create/update/upsert/search/delete operations, and record counts.
  ([#140](https://github.com/open-telemetry/semantic-conventions-genai/pull/140))
- Mark `gen_ai.agent.name` as sampling-relevant on `create_agent`, `invoke_agent` client, and `invoke_agent` internal spans.
  ([#107](https://github.com/open-telemetry/semantic-conventions-genai/pull/107))
- Add `plan` operation for GenAI agent planning/task decomposition spans.
  ([#97](https://github.com/open-telemetry/semantic-conventions-genai/pull/97))
- Add `gen_ai.workflow.duration` metric to track duration of a workflow.
  ([#126](https://github.com/open-telemetry/semantic-conventions-genai/pull/126))

### 🧰 Bug fixes 🧰

### 📚 Clarifications 📚
