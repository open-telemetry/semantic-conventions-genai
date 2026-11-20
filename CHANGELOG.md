# Changelog

## Unreleased

<!--
Do not add changelog entries here directly. This changelog is managed by
Towncrier; add fragments under changelog.d/ instead.
-->

<!-- towncrier release notes start -->

## v0.1.0

### 🛑 Breaking changes 🛑

- Change `gen_ai.request.top_k` type from `double` to `int` and scope it to
  decoding only. Retrieval spans now use the new `gen_ai.retrieval.top_k`
  attribute instead of `gen_ai.request.top_k`.
  ([#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217))
- Clarify `gen_ai.agent.id` stability expectations and scope; remove it from
  internal agent spans.
  ([#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242))
- Limit supported `gen_ai.system_instructions` part types to text.
  ([#257](https://github.com/open-telemetry/semantic-conventions-genai/pull/257))
- Remove `gen_ai.provider.name` required attribute from the `invoke_agent`
  internal span.
  ([#289](https://github.com/open-telemetry/semantic-conventions-genai/pull/289))
- Align `invoke_agent` and `execute_tool` semantic attributes across spans and
  duration metrics; remove `gen_ai.agent.version` from `invoke_agent` internal
  span; mark `execute_tool` sampling-relevant attributes
  ([#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322))
- Replace the `gen_ai.client.token.usage` histogram (and the
  `gen_ai.token.type` attribute it relied on) with separate per-direction,
  per-operation token usage histograms, so token distributions can be
  aggregated correctly.
  ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))
- Rename `gen_ai.usage.cache_creation.input_tokens` to
  `gen_ai.usage.cache_write.input_tokens`.
  ([#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440))
- Remove `gen_ai.usage.cache_read.input_tokens` and
  `gen_ai.usage.cache_write.input_tokens` from the internal `invoke_agent`
  span. Cache breakdowns on that span aggregate across models and inference
  calls, which makes them misleading; consumers should aggregate them from
  `gen_ai.inference.client` spans instead.
  ([#469](https://github.com/open-telemetry/semantic-conventions-genai/pull/469))
- Add `gen_ai.client.inference.duration` metric, consolidate inference client
  span, events and metrics in `client-inference.md`.

  Rename `gen_ai.client.operation.time_to_first_chunk` and
  `gen_ai.client.operation.time_per_output_chunk` to
  `gen_ai.client.inference.*`.

  Clarify that `gen_ai.client.operation.duration` is not for inference.
  ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))
- Merge the `invoke_workflow` span and metric into
  `gen_ai.invoke_agent.internal` and `gen_ai.invoke_agent.duration`. Replace
  `gen_ai.workflow.name` with `gen_ai.agent.name`.
  ([#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571))
- Use `gen_ai.client.inference.exception` instead of
  `gen_ai.client.operation.exception` for exceptions that cause client
  inference operations to fail.
  ([#658](https://github.com/open-telemetry/semantic-conventions-genai/pull/658))
- Use `gen_ai.client.embeddings.exception` instead of
  `gen_ai.client.operation.exception` for exceptions that cause client
  embeddings operations to fail.
  ([#659](https://github.com/open-telemetry/semantic-conventions-genai/pull/659))
- Use `gen_ai.client.invoke_agent.exception` instead of
  `gen_ai.client.operation.exception` for exceptions that cause client agent
  invocation operations to fail.
  ([#667](https://github.com/open-telemetry/semantic-conventions-genai/pull/667))
- Use `gen_ai.client.fetch_response.exception` instead of
  `gen_ai.client.operation.exception` for exceptions that cause client fetch
  response operations to fail.
  ([#669](https://github.com/open-telemetry/semantic-conventions-genai/pull/669))
- Remove `gen_ai.token.modality` from
  `gen_ai.client.inference.usage.reasoning.output_tokens`. Record the reasoning
  token count without a modality breakdown.
  ([#679](https://github.com/open-telemetry/semantic-conventions-genai/pull/679))
- Replace `gen_ai.prompt.variable` (`template[string]`) with
  `gen_ai.prompt.variables` (`any` object) to support structured and non-string
  prompt template variables, and remove prompt variables from MCP operation
  metrics.
  ([#677](https://github.com/open-telemetry/semantic-conventions-genai/issues/677))
  ([#696](https://github.com/open-telemetry/semantic-conventions-genai/pull/696))
- Add `gen_ai.client.embeddings.duration` and
  `gen_ai.client.embeddings.operation.input_tokens` metrics, consolidate
  embeddings client span and metrics in `client-embeddings.md`.

  Embeddings operations are no longer reported on
  `gen_ai.client.operation.duration` - use `gen_ai.client.embeddings.duration`
  instead. Embeddings token usage previously reported on
  `gen_ai.client.token.usage` is now reported on
  `gen_ai.client.embeddings.operation.input_tokens`.

  The embeddings input-token histogram includes failed operations and records
  zero when usage is unavailable, with `error.type` on failures.
- Add `gen_ai.client.invoke_agent.duration` metric.

  Invoke agent client operations are no longer reported on
  `gen_ai.client.operation.duration` - use
  `gen_ai.client.invoke_agent.duration` instead.
- Record the JSON-RPC error code on MCP spans and metrics with
  `rpc.status_code` instead of the deprecated `rpc.response.status_code`.
- Rename the `gen_ai.provider.name` value `mistral_ai` to `mistral` to match
  Mistral's brand name.
- Require structured values for JSON-schema-defined attributes on spans and
  events, removing the JSON-string fallback for spans.
- Retrieval operations are no longer reported on
  `gen_ai.client.operation.duration`.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))

### 🚩 Deprecations 🚩

- Deprecate `gen_ai.output.messages[].finish_reason` in favor of
  `gen_ai.response.finish_reasons`.
  ([#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363))
- Deprecate the `gen_ai.retrieval.client` span. Calls to retrieval or search
  services should follow database or other applicable client semantic
  conventions; retrieval performed by GenAI frameworks and applications should
  use the `gen_ai.retrieval` span.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))

### 🚀 New components 🚀

- Add A2A protocol semantic conventions for client/server spans, covering
  protocol, message,
  task, conversation, tenant, and Agent Card metadata attributes.
  Define A2A protocol error handling on HTTP and gRPC server spans, with
  transport
  errors taking precedence for independent transport failures. Prefer an
  available
  A2A error reason consistently across JSON-RPC, HTTP+JSON, and gRPC bindings,
  falling back to binding-specific error codes when the reason is unavailable.
  Omit task and conversation attributes when the operation has multiple
  distinct
  values, including task states observed across streaming events.
  ([#195](https://github.com/open-telemetry/semantic-conventions-genai/pull/195))

### 💡 Enhancements 💡

- Add `plan` operation for GenAI agent planning/task decomposition spans.
  ([#97](https://github.com/open-telemetry/semantic-conventions-genai/pull/97))
- Add `moonshot_ai` to `gen_ai.provider.name` well-known values.
  ([#99](https://github.com/open-telemetry/semantic-conventions-genai/pull/99))
- Mark `gen_ai.agent.name` as sampling-relevant on `create_agent`,
  `invoke_agent` client, and `invoke_agent` internal spans.
  ([#107](https://github.com/open-telemetry/semantic-conventions-genai/pull/107))
- Add `gen_ai.invoke_workflow.duration` metric to track duration of a workflow.
  ([#126](https://github.com/open-telemetry/semantic-conventions-genai/pull/126))
- Add GenAI memory operation span and attributes for memory store lifecycle
  (create/delete), memory record create/update/upsert/search/delete operations,
  and record counts.
  ([#140](https://github.com/open-telemetry/semantic-conventions-genai/pull/140))
- Add `document` value to the `Modality` enum in the GenAI
  input/output/system-instructions message JSON schemas. Enables capturing
  PDF/DOCX (and similar) parts that today have to fall through to the free-form
  `string` branch of the modality `anyOf`.
  ([#142](https://github.com/open-telemetry/semantic-conventions-genai/pull/142))
- Make `BlobPart.content` optional in the `gen_ai.input.messages` and
  `gen_ai.output.messages`.
  ([#144](https://github.com/open-telemetry/semantic-conventions-genai/pull/144))
- Add `gen_ai.conversation.compacted` on GenAI inference spans and
  `CompactionPart` message schema support for reporting compacted GenAI
  conversation context.
  ([#162](https://github.com/open-telemetry/semantic-conventions-genai/pull/162))
- Add `gen_ai.prompt.version` and `gen_ai.prompt.variable` attributes to
  enhance prompt tracking with version support and template variable recording.
  ([#137](https://github.com/open-telemetry/semantic-conventions-genai/issues/137))
  ([#179](https://github.com/open-telemetry/semantic-conventions-genai/pull/179))
- Add `gen_ai.invoke_agent.duration` metric to track the end-to-end duration of
  a single agent invocation, and `gen_ai.execute_tool.duration` metric to track
  the duration of a single tool execution.
  ([#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201))
- Add `gen_ai.request.reasoning.level` attribute to record the requested
  reasoning/thinking effort level for inference spans.
  ([#189](https://github.com/open-telemetry/semantic-conventions-genai/issues/189))
  ([#258](https://github.com/open-telemetry/semantic-conventions-genai/pull/258))
- Add `gen_ai.main_agent` entity definition and resource attributes, and update
  generator templates to support entity documentation.
  ([#270](https://github.com/open-telemetry/semantic-conventions-genai/pull/270))
- Clarify that `gen_ai.invoke_agent.duration` is about in-proc / internal span
  ([#321](https://github.com/open-telemetry/semantic-conventions-genai/pull/321))
- Move complex-attribute JSON serialization guidance into shared Jinja
  rendering templates and define JSON schema/type metadata via attribute
  annotations so it is discoverable by Weaver. Require every complex attribute
  to have schema defined.
  ([#330](https://github.com/open-telemetry/semantic-conventions-genai/pull/330))
- Add `gen_ai.invoke_agent.inference_calls` and
  `gen_ai.invoke_agent.tool_calls` metrics to track how many inference (model)
  and tool calls a GenAI agent makes during a single invocation.
  ([#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336))
- Add the `fetch_response` operation and `gen_ai.fetch_response.client` span
  for fetching a previously generated model response by its identifier without
  performing inference, with an OpenAI-specific refinement for the Responses
  API. The span also records `gen_ai.request.stream_cursor` when the fetch
  resumes a streamed response from a prior position, and
  `gen_ai.response.status` to capture the lifecycle status of the fetched
  response.
  ([#353](https://github.com/open-telemetry/semantic-conventions-genai/pull/353))
- Add `gen_ai.request.previous_response.id` attribute to reference a previous
  response or interaction ID when passing continuation context in multi-turn or
  follow-up operations.
  ([#372](https://github.com/open-telemetry/semantic-conventions-genai/pull/372))
- Add `gen_ai.client.inference.usage.*` token counters that let consumers
  aggregate token spend across operations, broken down by the new
  `gen_ai.token.modality` attribute and by token category (cached,
  cache-written, reasoning).
  ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))
- Add `realtime_inference` and `user_speech` operations and spans,
  `gen_ai.client.realtime_session.started`/`ended` events, the
  `gen_ai.realtime_session.id` attribute, and a `transcription` message part
  for realtime, bidirectional streaming sessions such as OpenAI Realtime and
  Gemini Live.
  ([#394](https://github.com/open-telemetry/semantic-conventions-genai/pull/394))
- Allow `gen_ai.conversation.id` on invoke workflow spans when available.
  ([#410](https://github.com/open-telemetry/semantic-conventions-genai/pull/410))
- Add per-modality token usage attributes:
  `gen_ai.usage.{text,image,audio}.{input_tokens,output_tokens}` and
  `gen_ai.usage.{text,image,audio}.cache_read.input_tokens`.
  ([#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440))
- Define `gen_ai.execute_tool.transfer.internal` for agent tool transfers with
  `gen_ai.transfer.mode` and `gen_ai.transfer.target.name`.
  ([#447](https://github.com/open-telemetry/semantic-conventions-genai/pull/447))
- Add `gen_ai.system_instructions_ref`, `gen_ai.input.messages_ref`,
  `gen_ai.output.messages_ref`, and `gen_ai.tool.definitions_ref` attributes
  referencing GenAI content stored externally.
  ([#490](https://github.com/open-telemetry/semantic-conventions-genai/pull/490))
- Mark `gen_ai.agent.name` as sampling-relevant on the `execute_tool` and
  `plan` spans.
  ([#495](https://github.com/open-telemetry/semantic-conventions-genai/pull/495))
- Add `gen_ai.skill.*` attributes recorded on the `execute_tool` span, so an
  agent's use of [Agent Skills](https://agentskills.io) — loading a skill's
  instructions, reading a bundled resource, running a bundled script — is
  described where the framework already exposes it, as a tool execution.
  ([#498](https://github.com/open-telemetry/semantic-conventions-genai/pull/498))
- Add `gen_ai.request.stream` to `gen_ai.fetch_response.client` and
  `gen_ai.invoke_agent.client` spans.
  ([#513](https://github.com/open-telemetry/semantic-conventions-genai/pull/513))
- Record the token usage histograms and usage counters for every inference
  operation, including failed ones, with `error.type` on the histograms and `0`
  when no usage was received.
  ([#536](https://github.com/open-telemetry/semantic-conventions-genai/pull/536))
- Define and formalize GenAI content capture and external storage upload
  configuration options.
  ([#543](https://github.com/open-telemetry/semantic-conventions-genai/pull/543))
- Add the `invoke_runner` operation name and the
  `invoke_{framework_entrypoint}` operation name pattern, and extend the
  recommended `gen_ai.invoke_agent.duration` buckets up to 24 hours.
  ([#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571))
- Make `gen_ai.client.inference.operation.details` event recommended instead of
  opt-in.
  ([#579](https://github.com/open-telemetry/semantic-conventions-genai/pull/579))
- Add `ollama` to `gen_ai.provider.name` well-known values.
  ([#663](https://github.com/open-telemetry/semantic-conventions-genai/pull/663))
- Add `gen_ai.execute_tool.exception` for exceptions that cause tool execution
  operations to fail.
  ([#668](https://github.com/open-telemetry/semantic-conventions-genai/pull/668))
- Add `gen_ai.invoke_agent.exception` for exceptions that cause internal agent
  invocation operations to fail.
  ([#670](https://github.com/open-telemetry/semantic-conventions-genai/pull/670))
- Add the `gen_ai.retrieval` internal span and `gen_ai.retrieval.duration`
  metric for retrieval performed by GenAI frameworks and applications.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))
- Allow `gen_ai.conversation.id` on `execute_tool` spans when available.

### 🧰 Bug fixes 🧰

- Add missing `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` opt-in
  attributes to MCP server span.
  ([#136](https://github.com/open-telemetry/semantic-conventions-genai/pull/136))
- Relax `gen_ai.provider.name` on `gen_ai.client.operation.duration` to
  `Conditionally Required`, to align with the `gen_ai.retrieval.client` and
  `gen_ai.memory.client` spans which already allow omitting
  `gen_ai.provider.name`.
  ([#214](https://github.com/open-telemetry/semantic-conventions-genai/pull/214))
- Clarify MCP error reporting: MCP server telemetry no longer reports
  client-side errors as failures, while MCP client telemetry reports all
  JSON-RPC error codes as errors.
  ([#389](https://github.com/open-telemetry/semantic-conventions-genai/pull/389))
- Reject malformed known message parts in JSON schemas and recommend prefixing
  custom part types with `gen_ai.provider.name`.

  - Exclude defined part `type` values from `GenericPart` in the
  `gen_ai.input.messages`, `gen_ai.output.messages`, and
  `gen_ai.system_instructions` JSON schemas so parts with a known `type` must
  match that part's schema.
  - Recommend prefixing provider-specific part `type` values in
  `gen_ai.input.messages`, `gen_ai.output.messages`, and
  `gen_ai.system_instructions` with `gen_ai.provider.name` (for example
  `anthropic.search_result`).

([#584](https://github.com/open-telemetry/semantic-conventions-genai/pull/584))
- Reject malformed `function` tool definitions in `gen_ai.tool.definitions`
  JSON schema and recommend prefixing custom tool definition types with
  `gen_ai.provider.name`.

  - Exclude defined tool definition `type` values (`function`) from
  `GenericToolDefinition` so tool definitions with a known `type` must match
  that tool definition's schema.
  - Recommend prefixing provider-specific tool definition `type` values with
  `gen_ai.provider.name` (for example `anthropic.web_search_20250305`).

([#608](https://github.com/open-telemetry/semantic-conventions-genai/pull/608))
- Make retrieval document `id` and `score` optional so instrumentations can
  omit values that are unavailable at runtime.
- Record only known, strictly positive contributions on all five
  `gen_ai.client.inference.usage.*` counters, including usage from failed
  operations. Do not record zero-valued measurements or unavailable counts.
- Remove per-operation transport details from MCP session-duration metrics.

### 📚 Clarifications 📚

- Clarify that when a provider reports both billed and consumed token counts
  (for example, Cohere), `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens` SHOULD report the billed counts.
  ([#211](https://github.com/open-telemetry/semantic-conventions-genai/pull/211))
- Generalize the `gen_ai.provider.name` description: remove inference-centric
  paragraphs, and add guidance for per-operation semantic conventions to
  clarify which kinds of providers apply when it is not clear from context.
  ([#212](https://github.com/open-telemetry/semantic-conventions-genai/pull/212))
- Clarify that a GenAI span SHOULD cover the duration of the operation as
  observed by the caller, including any retries.
  ([#216](https://github.com/open-telemetry/semantic-conventions-genai/pull/216))
- Clarify that `gen_ai.request.top_k` is the top-K sampling/decoding parameter
  (e.g., Anthropic `top_k`, Cohere `k`) and not OpenAI's `top_logprobs`
  output-shaping parameter.
  ([#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217))
- Clarify that `gen_ai.conversation.id` should only be populated from an
  available conversation identifier, and that instrumentations should not use
  fallback values such as generated UUIDs, trace IDs, or request-content
  hashes.
  ([#219](https://github.com/open-telemetry/semantic-conventions-genai/pull/219))
- Clarify MCP context propagation now that SEP-414 defines `traceparent`,
  `tracestate`, and `baggage` as unprefixed `params._meta` keys.
  ([#220](https://github.com/open-telemetry/semantic-conventions-genai/pull/220))
- Clarify when instrumentations should report `gen_ai.invoke_workflow` spans,
  add per-framework examples, and tighten the guidance on what
  `gen_ai.workflow.name` should contain.
  ([#354](https://github.com/open-telemetry/semantic-conventions-genai/pull/354))
- Fix reference scenarios to use schema-compatible `gen_ai.system_instructions`
  values and keep message-channel system instructions in
  `gen_ai.input.messages`.
  ([#361](https://github.com/open-telemetry/semantic-conventions-genai/pull/361))
- Clarify positional correspondence in `gen_ai.response.finish_reasons` and use
  `error` when an expected finish reason is not received.
  ([#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363))
- Clarify how MCP records JSON-RPC error codes with `error.type` and
  `rpc.response.status_code`.
  ([#452](https://github.com/open-telemetry/semantic-conventions-genai/pull/452))
- Clarify content-upload hook behavior for failed GenAI operations.
  ([#459](https://github.com/open-telemetry/semantic-conventions-genai/pull/459))
- Make `gen_ai.tool.call.id` conditionally required on `execute_tool` if and
  only if the model or provider supplied an identifier.
  ([#489](https://github.com/open-telemetry/semantic-conventions-genai/pull/489))
- Add guidance that `gen_ai.client.inference.operation.details` event severity
  should be set to DEBUG (severity number 5).
  ([#520](https://github.com/open-telemetry/semantic-conventions-genai/pull/520))
- Clarify that `gen_ai.invoke_agent.client` SHOULD be emitted for
  out-of-process agent invocations and `gen_ai.invoke_agent.internal` SHOULD be
  emitted for in-process agent execution.
  ([#524](https://github.com/open-telemetry/semantic-conventions-genai/pull/524))
- Clarify that optional token usage breakdown attributes (cache, reasoning, and
  per-modality counts) are recommended only when available and non-zero.
  ([#548](https://github.com/open-telemetry/semantic-conventions-genai/pull/548))
- Clarify in-process propagation of shared GenAI attributes, including
  preference for values from the instrumented library and use only on signals
  that explicitly reference them.
  ([#556](https://github.com/open-telemetry/semantic-conventions-genai/pull/556))
- Clarify that `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are
  totals across all modalities. Per-modality attributes on spans and events are
  recommended only when the provider reports them. On usage metrics,
  instrumentations SHOULD record tokens with no known modality as `unknown`.
  ([#560](https://github.com/open-telemetry/semantic-conventions-genai/pull/560))
- Clarify that the client inference span may have nested spans recorded by the
  model provider, and that its `gen_ai.response.model`, `gen_ai.response.id`
  and usage attributes reflect what the model provider returns for this
  inference operation.
  ([#562](https://github.com/open-telemetry/semantic-conventions-genai/pull/562))
- Clarify the first response chunk and measurement boundaries, including
  authentication and retries, for the GenAI time-to-first-chunk metric and span
  attribute.
  ([#617](https://github.com/open-telemetry/semantic-conventions-genai/pull/617))
- Clarify that `gen_ai.invoke_agent.inference_calls` counts each logical
  inference operation once, regardless of retries.
  ([#665](https://github.com/open-telemetry/semantic-conventions-genai/pull/665))
- Clarify the scope of `gen_ai.tool.definitions` on inference, realtime
  inference, agent-invocation, and fetch-response spans.
  ([#721](https://github.com/open-telemetry/semantic-conventions-genai/pull/721))
- Clarify that `gen_ai.usage.*` span attributes are not additive across spans
  of different types; token usage metrics should be used whenever possible.
  ([#736](https://github.com/open-telemetry/semantic-conventions-genai/pull/736))
- Clarify how MCP instrumentation records HTTP failures without JSON-RPC error
  codes.
- Consolidate execute tool span, specialized tool call span, and duration
  metric conventions, and clarify that execute tool operations use
  `gen_ai.execute_tool.duration` instead of `gen_ai.client.operation.duration`.
- Mark `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`,
  `gen_ai.retrieval.documents`, and `gen_ai.memory.records` as unbounded in
  size.
- Warn that `gen_ai.tool.description` and `gen_ai.tool.definitions` may contain
  sensitive information.
