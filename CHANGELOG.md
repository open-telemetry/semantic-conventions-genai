# Changelog

## Unreleased

<!--
Do not add changelog entries here directly. This changelog is managed by
Towncrier; add fragments under changelog.d/ instead.
-->

<!-- towncrier release notes start -->

## v0.1.0

First standalone release of the GenAI semantic conventions. Lists changes since
[semantic-conventions v1.41.0](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/README.md),
the last release before GenAI conventions moved to this repository. Depends on
semantic-conventions v1.45.0.

### 🛑 Breaking changes 🛑

- Merge the `invoke_workflow` span into `gen_ai.invoke_agent.internal` and
  record workflows on `gen_ai.invoke_agent.duration`; `gen_ai.operation.name`
  stays `invoke_workflow`. Replace `gen_ai.workflow.name` with
  `gen_ai.agent.name`.
  ([#126](https://github.com/open-telemetry/semantic-conventions-genai/pull/126))
  ([#354](https://github.com/open-telemetry/semantic-conventions-genai/pull/354))
  ([#410](https://github.com/open-telemetry/semantic-conventions-genai/pull/410))
  ([#571](https://github.com/open-telemetry/semantic-conventions-genai/pull/571))
- Change `gen_ai.request.top_k` type from `double` to `int` and scope it to
  the top-K sampling/decoding parameter (e.g., Anthropic `top_k`, Cohere `k`),
  not OpenAI's `top_logprobs`. Retrieval spans now use the new
  `gen_ai.retrieval.top_k` attribute instead of `gen_ai.request.top_k`.
  ([#217](https://github.com/open-telemetry/semantic-conventions-genai/pull/217))
- Clarify `gen_ai.agent.id` stability expectations and scope; remove it from
  internal agent spans.
  ([#242](https://github.com/open-telemetry/semantic-conventions-genai/pull/242))
- Limit the predefined `gen_ai.system_instructions` part types to `text`.
  Provider-specific part types are still supported.
  ([#257](https://github.com/open-telemetry/semantic-conventions-genai/pull/257))
- Remove `gen_ai.provider.name` required attribute from the `invoke_agent`
  internal span.
  ([#289](https://github.com/open-telemetry/semantic-conventions-genai/pull/289))
- Align `invoke_agent` and `execute_tool` semantic attributes across spans and
  duration metrics; remove `gen_ai.agent.version` from `invoke_agent` internal
  span; mark `execute_tool` sampling-relevant attributes.
  ([#322](https://github.com/open-telemetry/semantic-conventions-genai/pull/322))
- Replace the `gen_ai.client.token.usage` histogram and its
  `gen_ai.token.type` attribute with the
  `gen_ai.client.inference.operation.input_tokens` and
  `gen_ai.client.inference.operation.output_tokens` histograms for inference.
  When reporting these histograms, cover each inference operation and set
  `error.type` on failures. Use `0` if the response is missing or contains no
  token usage.
  ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))
  ([#536](https://github.com/open-telemetry/semantic-conventions-genai/pull/536))
- Rename `gen_ai.usage.cache_creation.input_tokens` to
  `gen_ai.usage.cache_write.input_tokens`.
  ([#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440))
- Record the JSON-RPC error code on MCP spans and operation metrics with
  `rpc.status_code` instead of the deprecated `rpc.response.status_code`.
  ([#452](https://github.com/open-telemetry/semantic-conventions-genai/pull/452))
  ([#732](https://github.com/open-telemetry/semantic-conventions-genai/pull/732))
- Remove `network.transport` and `network.protocol.version` from
  `mcp.client.session.duration` and `mcp.server.session.duration`. Both
  attributes are still available on MCP operation-duration metrics.
  ([#453](https://github.com/open-telemetry/semantic-conventions-genai/pull/453))
- Remove `gen_ai.usage.cache_read.input_tokens` and
  `gen_ai.usage.cache_write.input_tokens` from the internal `invoke_agent`
  span. Read cache usage from `gen_ai.client.inference` spans or the
  `gen_ai.client.inference.usage.*` metrics instead.
  ([#469](https://github.com/open-telemetry/semantic-conventions-genai/pull/469))
- Rename the `gen_ai.provider.name` value `mistral_ai` to `mistral` to match
  Mistral's brand name.
  ([#506](https://github.com/open-telemetry/semantic-conventions-genai/pull/506))
- Add `gen_ai.client.inference.duration` metric, consolidate inference client
  span, events and metrics in `client-inference.md`.

  Inference operations are no longer reported on
  `gen_ai.client.operation.duration`; use `gen_ai.client.inference.duration`
  instead. Rename `gen_ai.client.operation.time_to_first_chunk` and
  `gen_ai.client.operation.time_per_output_chunk` to
  `gen_ai.client.inference.time_to_first_chunk` and
  `gen_ai.client.inference.time_per_output_chunk`.
  ([#521](https://github.com/open-telemetry/semantic-conventions-genai/pull/521))
- Add `gen_ai.client.embeddings.duration` and
  `gen_ai.client.embeddings.operation.input_tokens` metrics, consolidate
  embeddings client span and metrics in `client-embeddings.md`.

  Embeddings operations are no longer reported on
  `gen_ai.client.operation.duration`; use `gen_ai.client.embeddings.duration`
  instead. Embeddings token usage previously reported on
  `gen_ai.client.token.usage` is now reported on
  `gen_ai.client.embeddings.operation.input_tokens`.

  The embeddings input-token histogram includes failed operations and records
  zero when usage is unavailable, with `error.type` on failures.
  ([#578](https://github.com/open-telemetry/semantic-conventions-genai/pull/578))
- Reject malformed known parts in the `gen_ai.input.messages`,
  `gen_ai.output.messages`, and `gen_ai.system_instructions` JSON schemas, and
  malformed `function` definitions in `gen_ai.tool.definitions`. These no
  longer pass validation as generic entries. For provider-specific types,
  `gen_ai.provider.name` is the recommended prefix.
  ([#584](https://github.com/open-telemetry/semantic-conventions-genai/pull/584))
  ([#608](https://github.com/open-telemetry/semantic-conventions-genai/pull/608))
- Require structured values for JSON-schema-defined attributes on spans and
  events, removing the JSON-string fallback for spans.
  ([#634](https://github.com/open-telemetry/semantic-conventions-genai/pull/634))
- Add `gen_ai.client.invoke_agent.duration` metric.

  Invoke agent client operations are no longer reported on
  `gen_ai.client.operation.duration`; use
  `gen_ai.client.invoke_agent.duration` instead.
  ([#635](https://github.com/open-telemetry/semantic-conventions-genai/pull/635))
- Execute tool operations are no longer reported on
  `gen_ai.client.operation.duration`; use `gen_ai.execute_tool.duration`
  instead. Consolidate execute tool span, specialized tool call span, and
  duration metric conventions in `execute-tool.md`.
  ([#636](https://github.com/open-telemetry/semantic-conventions-genai/pull/636))
- Retrieval operations are no longer reported on
  `gen_ai.client.operation.duration`.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))
  ([#643](https://github.com/open-telemetry/semantic-conventions-genai/pull/643))
- Use `gen_ai.client.inference.exception`,
  `gen_ai.client.embeddings.exception`, and
  `gen_ai.client.invoke_agent.exception` instead of
  `gen_ai.client.operation.exception` for exceptions that cause client
  inference, embeddings, and agent invocation operations to fail.
  ([#658](https://github.com/open-telemetry/semantic-conventions-genai/pull/658))
  ([#659](https://github.com/open-telemetry/semantic-conventions-genai/pull/659))
  ([#667](https://github.com/open-telemetry/semantic-conventions-genai/pull/667))

### 🚩 Deprecations 🚩

- Deprecate `gen_ai.output.messages[].finish_reason` in favor of
  `gen_ai.response.finish_reasons`.
  ([#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363))
- Deprecate the `gen_ai.retrieval.client` span. Calls to retrieval or search
  services should follow database or other applicable client semantic
  conventions; retrieval performed by GenAI frameworks and applications should
  use the `gen_ai.retrieval` span.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))
  ([#645](https://github.com/open-telemetry/semantic-conventions-genai/pull/645))

### 🚀 New components 🚀

- Add A2A protocol semantic conventions for client and server spans, covering
  protocol, message, task, conversation, tenant, and Agent Card metadata
  attributes, and A2A error reporting across the JSON-RPC, HTTP+JSON, and
  gRPC bindings.
  ([#195](https://github.com/open-telemetry/semantic-conventions-genai/pull/195))

### 💡 Enhancements 💡

- Add `plan` operation for GenAI agent planning/task decomposition spans.
  ([#97](https://github.com/open-telemetry/semantic-conventions-genai/pull/97))
- Add `moonshot_ai` to `gen_ai.provider.name` well-known values.
  ([#99](https://github.com/open-telemetry/semantic-conventions-genai/pull/99))
- Mark `gen_ai.agent.name` as sampling-relevant on `create_agent`,
  `invoke_agent` client, `invoke_agent` internal, `execute_tool`, and `plan`
  spans.
  ([#107](https://github.com/open-telemetry/semantic-conventions-genai/pull/107))
  ([#495](https://github.com/open-telemetry/semantic-conventions-genai/pull/495))
- Add GenAI memory operation span and attributes for memory store lifecycle
  (create/delete), memory record create/update/upsert/search/delete operations,
  and record counts.
  ([#140](https://github.com/open-telemetry/semantic-conventions-genai/pull/140))
- Add `document` value to the `Modality` enum in the `gen_ai.input.messages`
  and `gen_ai.output.messages` JSON schemas, for PDF, DOCX, and similar parts.
  ([#142](https://github.com/open-telemetry/semantic-conventions-genai/pull/142))
- Make `BlobPart.content` optional in the `gen_ai.input.messages` and
  `gen_ai.output.messages` JSON schemas.
  ([#144](https://github.com/open-telemetry/semantic-conventions-genai/pull/144))
- Add `gen_ai.conversation.compacted` on GenAI inference spans and
  `CompactionPart` message schema support for reporting compacted GenAI
  conversation context.
  ([#162](https://github.com/open-telemetry/semantic-conventions-genai/pull/162))
- Add `gen_ai.prompt.version` for the template version and
  `gen_ai.prompt.variables` for variables as a structured object. In MCP,
  variables are opt-in on `prompts/get` spans and not recorded on operation
  metrics.
  ([#137](https://github.com/open-telemetry/semantic-conventions-genai/issues/137))
  ([#179](https://github.com/open-telemetry/semantic-conventions-genai/pull/179))
  ([#677](https://github.com/open-telemetry/semantic-conventions-genai/issues/677))
  ([#696](https://github.com/open-telemetry/semantic-conventions-genai/pull/696))
- Add `gen_ai.invoke_agent.duration` metric to track the end-to-end duration of
  a single in-process agent invocation, and
  `gen_ai.execute_tool.duration` metric to track the duration of a single tool
  execution.
  ([#201](https://github.com/open-telemetry/semantic-conventions-genai/pull/201))
  ([#321](https://github.com/open-telemetry/semantic-conventions-genai/pull/321))
- Add `gen_ai.request.reasoning.level` attribute to record the requested
  reasoning/thinking effort level for inference spans.
  ([#189](https://github.com/open-telemetry/semantic-conventions-genai/issues/189))
  ([#258](https://github.com/open-telemetry/semantic-conventions-genai/pull/258))
- Add `gen_ai.main_agent` entity definition and resource attributes.
  ([#270](https://github.com/open-telemetry/semantic-conventions-genai/pull/270))
- Require every complex attribute to define a JSON schema.
  ([#330](https://github.com/open-telemetry/semantic-conventions-genai/pull/330))
- Add `gen_ai.invoke_agent.inference_calls` and
  `gen_ai.invoke_agent.tool_calls` metrics to track how many inference (model)
  and tool calls a GenAI agent makes during a single invocation. Each logical
  inference operation counts once, regardless of retries.
  ([#336](https://github.com/open-telemetry/semantic-conventions-genai/pull/336))
  ([#665](https://github.com/open-telemetry/semantic-conventions-genai/pull/665))
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
- Add the `gen_ai.client.inference.usage.input_tokens`,
  `gen_ai.client.inference.usage.output_tokens`,
  `gen_ai.client.inference.usage.cache_read.input_tokens`,
  `gen_ai.client.inference.usage.cache_write.input_tokens`, and
  `gen_ai.client.inference.usage.reasoning.output_tokens` counters for
  aggregating token usage across operations. All except the reasoning counter
  require `gen_ai.token.modality`, which MUST be `unknown` when the modality
  cannot reliably be determined. Record only known, positive counts, including
  from failed operations.
  ([#374](https://github.com/open-telemetry/semantic-conventions-genai/pull/374))
  ([#602](https://github.com/open-telemetry/semantic-conventions-genai/pull/602))
  ([#679](https://github.com/open-telemetry/semantic-conventions-genai/pull/679))
- Add `realtime_inference` and `user_speech` operations and spans,
  `gen_ai.client.realtime_session.started`/`ended` events, the
  `gen_ai.realtime_session.id` attribute, and a `transcription` message part
  for realtime, bidirectional streaming sessions such as OpenAI Realtime and
  Gemini Live.
  ([#394](https://github.com/open-telemetry/semantic-conventions-genai/pull/394))
- Add per-modality token usage attributes:
  `gen_ai.usage.{text,image,audio}.{input_tokens,output_tokens}` and
  `gen_ai.usage.{text,image,audio}.cache_read.input_tokens`.
  ([#440](https://github.com/open-telemetry/semantic-conventions-genai/pull/440))
- Define `gen_ai.execute_tool.transfer` for agent tool transfers with
  `gen_ai.transfer.mode` and `gen_ai.transfer.target.name`.
  ([#447](https://github.com/open-telemetry/semantic-conventions-genai/pull/447))
- Add `gen_ai.system_instructions_ref`, `gen_ai.input.messages_ref`,
  `gen_ai.output.messages_ref`, and `gen_ai.tool.definitions_ref` attributes
  referencing GenAI content stored externally.
  ([#490](https://github.com/open-telemetry/semantic-conventions-genai/pull/490))
- Add `gen_ai.skill.*` attributes on the `execute_tool` span to describe an
  agent's use of [Agent Skills](https://agentskills.io), and add `load_skill`,
  `read_skill_resource`, and `command` `execute_tool` span refinements. The
  `command` refinement records `process.*` attributes.
  ([#498](https://github.com/open-telemetry/semantic-conventions-genai/pull/498))
- Add `gen_ai.request.stream` to `gen_ai.fetch_response.client` and
  `gen_ai.client.invoke_agent` spans.
  ([#513](https://github.com/open-telemetry/semantic-conventions-genai/pull/513))
- Allow `gen_ai.conversation.id` on `execute_tool` spans when available.
  ([#518](https://github.com/open-telemetry/semantic-conventions-genai/pull/518))
- Make `gen_ai.tool.call.id` conditionally required on `execute_tool` if and
  only if the model or provider supplied an identifier.
  ([#489](https://github.com/open-telemetry/semantic-conventions-genai/issues/489))
  ([#525](https://github.com/open-telemetry/semantic-conventions-genai/pull/525))
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
- Add the `gen_ai.retrieval` internal span and `gen_ai.retrieval.duration`
  metric for retrieval performed by GenAI frameworks and applications.
  ([#637](https://github.com/open-telemetry/semantic-conventions-genai/issues/637))
  ([#644](https://github.com/open-telemetry/semantic-conventions-genai/pull/644))
- Add `ollama` to `gen_ai.provider.name` well-known values.
  ([#663](https://github.com/open-telemetry/semantic-conventions-genai/pull/663))
- Add `gen_ai.client.fetch_response.exception`, `gen_ai.execute_tool.exception`,
  and `gen_ai.invoke_agent.exception` events for exceptions that cause client
  fetch response, tool execution, and internal agent invocation operations to
  fail.
  ([#668](https://github.com/open-telemetry/semantic-conventions-genai/pull/668))
  ([#669](https://github.com/open-telemetry/semantic-conventions-genai/pull/669))
  ([#670](https://github.com/open-telemetry/semantic-conventions-genai/pull/670))

### 🧰 Bug fixes 🧰

- Add missing `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` opt-in
  attributes to MCP server span.
  ([#136](https://github.com/open-telemetry/semantic-conventions-genai/pull/136))
- Relax `gen_ai.provider.name` on `gen_ai.client.operation.duration` to
  `Conditionally Required`. Record it when the operation calls a GenAI
  provider.
  ([#214](https://github.com/open-telemetry/semantic-conventions-genai/pull/214))
- Make retrieval document `id` and `score` optional so instrumentations can
  omit values that are unavailable at runtime.
  ([#396](https://github.com/open-telemetry/semantic-conventions-genai/pull/396))
- Clarify MCP error reporting: MCP server telemetry no longer reports
  client-side errors as failures, while MCP client telemetry reports all
  JSON-RPC error codes as errors.
  ([#389](https://github.com/open-telemetry/semantic-conventions-genai/issues/389))
  ([#404](https://github.com/open-telemetry/semantic-conventions-genai/pull/404))

### 📚 Clarifications 📚

- Remove the `OTEL_SEMCONV_STABILITY_OPT_IN` transition guidance for
  instrumentations using GenAI conventions v1.36.0 or earlier.
  ([#198](https://github.com/open-telemetry/semantic-conventions-genai/pull/198))
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
- Clarify that `gen_ai.conversation.id` should only be populated from an
  available conversation identifier, and that instrumentations should not use
  fallback values such as generated UUIDs, trace IDs, or request-content
  hashes.
  ([#219](https://github.com/open-telemetry/semantic-conventions-genai/pull/219))
- Clarify MCP context propagation now that SEP-414 defines `traceparent`,
  `tracestate`, and `baggage` as unprefixed `params._meta` keys.
  ([#220](https://github.com/open-telemetry/semantic-conventions-genai/pull/220))
- Clarify positional correspondence in `gen_ai.response.finish_reasons` and use
  `error` when an expected finish reason is not received.
  ([#363](https://github.com/open-telemetry/semantic-conventions-genai/pull/363))
- Warn that `gen_ai.tool.description` and `gen_ai.tool.definitions` may contain
  sensitive information.
  ([#431](https://github.com/open-telemetry/semantic-conventions-genai/pull/431))
- Clarify how MCP instrumentation records HTTP failures without JSON-RPC error
  codes.
  ([#458](https://github.com/open-telemetry/semantic-conventions-genai/pull/458))
- Clarify content-upload hook behavior for failed GenAI operations.
  ([#459](https://github.com/open-telemetry/semantic-conventions-genai/pull/459))
- Add guidance that `gen_ai.client.inference.operation.details` event severity
  should be set to DEBUG (severity number 5).
  ([#520](https://github.com/open-telemetry/semantic-conventions-genai/pull/520))
- Clarify that `gen_ai.client.invoke_agent` SHOULD be emitted for
  out-of-process agent invocations and `gen_ai.invoke_agent.internal` SHOULD be
  emitted for in-process agent execution.
  ([#524](https://github.com/open-telemetry/semantic-conventions-genai/pull/524))
- Clarify that `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are
  totals across all modalities. Cache and reasoning breakdowns are recommended
  when available and non-zero. Per-modality breakdowns are recommended when
  the provider reports non-zero counts.
  ([#548](https://github.com/open-telemetry/semantic-conventions-genai/pull/548))
  ([#560](https://github.com/open-telemetry/semantic-conventions-genai/pull/560))
- Clarify in-process propagation of shared GenAI attributes, including
  preference for values from the instrumented library and use only on signals
  that explicitly reference them.
  ([#556](https://github.com/open-telemetry/semantic-conventions-genai/pull/556))
- Clarify that the client inference span may have nested spans recorded by the
  model provider, and that its `gen_ai.response.model`, `gen_ai.response.id`
  and usage attributes reflect what the model provider returns for this
  inference operation.
  ([#562](https://github.com/open-telemetry/semantic-conventions-genai/pull/562))
- Mark `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`,
  `gen_ai.retrieval.documents`, and `gen_ai.memory.records` as unbounded in
  size.
  ([#606](https://github.com/open-telemetry/semantic-conventions-genai/pull/606))
- Clarify the first response chunk and measurement boundaries, including
  authentication and retries, for the GenAI time-to-first-chunk metric and span
  attribute.
  ([#617](https://github.com/open-telemetry/semantic-conventions-genai/pull/617))
- Clarify the scope of `gen_ai.tool.definitions` on inference, realtime
  inference, agent-invocation, and fetch-response spans.
  ([#721](https://github.com/open-telemetry/semantic-conventions-genai/pull/721))
- Clarify that `gen_ai.usage.*` span attributes are not additive across spans
  of different types; token usage metrics should be used whenever possible.
  ([#736](https://github.com/open-telemetry/semantic-conventions-genai/pull/736))
