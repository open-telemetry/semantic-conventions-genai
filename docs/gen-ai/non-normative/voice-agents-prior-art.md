<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Voice agents prior art
--->

<!-- I'm an AI agent!!! -->

# Voice agents: prior art and breadth survey

**Status**: [Development][DocumentStatus]

This is a non-normative supporting document. It records the breadth-first / prior
art investigation behind the GenAI voice agent conventions (see
[Voice agents](../gen-ai-voice-agents.md)), as required by the repository
contribution guidance ("Investigate breadth first" and the pull request
"Prior art" field). It surveys how existing voice agent frameworks and STT / TTS
/ realtime provider APIs model the same telemetry, so that the proposed
conventions work broadly across the ecosystem rather than for a single SDK.

<!-- toc -->

- [Scope](#scope)
- [Coverage matrix](#coverage-matrix)
- [Cascade frameworks](#cascade-frameworks)
  - [Pipecat](#pipecat)
  - [LiveKit Agents](#livekit-agents)
- [Realtime (voice-native) provider APIs](#realtime-voice-native-provider-apis)
  - [Google Gemini Live](#google-gemini-live)
  - [Azure Voice Live](#azure-voice-live)
- [Dedicated STT / TTS providers](#dedicated-stt--tts-providers)
  - [Deepgram](#deepgram)
  - [ElevenLabs](#elevenlabs)
- [Mapping to the proposed conventions](#mapping-to-the-proposed-conventions)
- [Whole-conversation audio and session modeling](#whole-conversation-audio-and-session-modeling)
- [Open questions](#open-questions)
- [Instrumentation gaps](#instrumentation-gaps)
- [References](#references)

<!-- tocstop -->

## Scope

Three reference sources anchored the original proposal: the OpenAI Agents voice
pipeline ([openai-agents-python#265](https://github.com/openai/openai-agents-python/pull/265)),
Arize OpenInference realtime audio tracing
([openinference#3173](https://github.com/Arize-ai/openinference/pull/3173)), and
the [Hamming voice-agent OpenTelemetry guide](https://hamming.ai/resources/opentelemetry-voice-agents-tracing-guide).
To avoid over-fitting to those, this survey adds six further libraries and
provider APIs across the two voice agent architectures:

- **Cascade / pipeline** (separate STT → LLM → TTS stages): Pipecat, LiveKit Agents.
- **Realtime / voice-native** (single bidirectional speech-to-speech model):
  Google Gemini Live, Azure Voice Live.
- **Dedicated STT / TTS providers** (the concrete stages a cascade agent calls):
  Deepgram, ElevenLabs.

## Coverage matrix

| Library | Architecture | Native OpenTelemetry? | Reuses `gen_ai.*`? |
|---|---|---|---|
| Pipecat | Cascade + realtime | Yes | Yes — `gen_ai.operation.name` = `stt` / `tts` / `chat` |
| LiveKit Agents | Cascade + realtime | Yes (traces + metrics) | Yes — including audio-token attributes |
| Google Gemini Live | Realtime | None found | API only |
| Azure Voice Live | Realtime | Partial (via OpenLLMetry OpenAI Realtime wrappers) | Partial |
| Deepgram | Cascade STT / TTS | None found | API only |
| ElevenLabs | Cascade STT / TTS (+ ConvAI) | None found | API only |

Each provider section below adds two mapping tables: **spans** (the provider's
span or protocol concept → the `gen_ai.*` span / operation it corresponds to) and
**attributes** (the provider's field → the `gen_ai.*` attribute it maps to). In
the attribute tables, `—` means there is no `gen_ai.*` equivalent today; where a
mapping depends on a not-yet-accepted addition, it is called out inline and
tracked in [Mapping to the proposed conventions](#mapping-to-the-proposed-conventions).

## Cascade frameworks

### Pipecat

- **Tracing**: native, opt-in OpenTelemetry under `pipecat.utils.tracing`.
- **Span hierarchy**: `conversation` → `turn` → `stt` / `llm` / `tts` (one `turn`
  per user→agent exchange).
- **Attributes**: reuses `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.operation.name` (`stt` / `tts` / `chat`), `gen_ai.output.type = speech`,
  and `gen_ai.usage.{input,output}_tokens`. Voice-specific fields are flat and
  non-`gen_ai`: `voice_id`, `language`, `is_final`, `vad_enabled`,
  `metrics.ttfb`, `metrics.character_count`.
- **Barge-in**: booleans — `turn.was_interrupted` (turn span),
  `tts.interrupted` (TTS span), plus `turn.ended_by_conversation_end`.
- **Latency**: `metrics.ttfb` per stage (from request issuance) and
  `turn.user_bot_latency_seconds` (user silence → first bot audio).
- **Realtime**: same `conversation → turn` hierarchy with realtime-specific
  operation values (`setup`, `model_turn`, `transcription`, `response`).

The tables below map Pipecat's tracing surface span-by-span. Pipecat's spans are
created in `src/pipecat/utils/tracing/turn_trace_observer.py` (conversation,
turn) and `service_decorators.py` / `service_attributes.py` (stt, llm, tts, and
the realtime spans). Notably, Pipecat's `llm` span already sets most `gen_ai.*`
chat attributes verbatim, so much of the mapping is identity.

**Span hierarchy → `gen_ai.*`**

| Pipecat span | `gen_ai.*` span / operation |
|---|---|
| `conversation` (tracer `pipecat.turn`) | not a span — session correlation via `gen_ai.conversation.id` |
| `turn` (tracer `pipecat.turn`) | `invoke_agent` (per-turn container over the stage spans) |
| `stt` | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `llm` | `chat` |
| `tts` | `gen_ai.text_to_speech.client` (`text_to_speech`) |
| realtime `llm_setup` / `llm_request` / `llm_response` / `llm_tool_call` / `llm_tool_result` (Gemini Live, OpenAI Realtime) | conversation turn under `invoke_agent`; tool ops → `execute_tool` |

Pipecat's `turn` span is the per-exchange container that nests the `stt`, `llm`,
and `tts` stage spans, which is exactly the role the voice conventions give the
[invoke agent](../gen-ai-agent-spans.md#invoke-agent-internal-span) span ("the
container for one turn"). Pipecat's outer `conversation` span spans the whole
multi-turn session; the GenAI conventions model that as the
`gen_ai.conversation.id` correlation attribute rather than a dedicated span.

**`conversation` span attributes** (→ carried as attributes, not a span)

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `conversation.id` | `gen_ai.conversation.id` (set on the `invoke_agent` turn span and its children) |
| `conversation.type` (`"voice"`) | — (no `gen_ai.*` equivalent) |
| `additional_span_attributes.*` | — (user-supplied resource/context) |

**`turn` span attributes** → `invoke_agent`

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `turn.was_interrupted` (`True`) | `gen_ai.agent.invocation.end_reason = interrupted` |
| `turn.ended_by_conversation_end` (`True`) | `gen_ai.agent.invocation.end_reason = session_closed` |
| `turn.number` | — (turn index; no `gen_ai.*` equivalent) |
| `turn.type` (`"conversation"`) | — |
| `turn.duration_seconds` | — (captured by span duration) |
| `turn.user_bot_latency_seconds` | — (perceived voice latency; no stable `gen_ai.*` attribute yet) |
| `conversation.id` | `gen_ai.conversation.id` |

**`stt` span attributes** → `gen_ai.speech_to_text.client`

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `gen_ai.provider.name` | `gen_ai.provider.name` (same) |
| `gen_ai.request.model` | `gen_ai.request.model` (same) |
| `gen_ai.operation.name` (`"stt"`) | `gen_ai.operation.name = speech_to_text` |
| `language` | `gen_ai.speech.input.language` |
| `transcript` | recorded as transcript message content |
| `metrics.ttfb` | — (voice latency; no stable `gen_ai.*` attribute yet) |
| `is_final`, `stt.incomplete`, `user_id`, `vad_enabled`, `settings.*` | — (streaming / VAD / per-service detail) |

**`tts` span attributes** → `gen_ai.text_to_speech.client`

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `gen_ai.provider.name` | `gen_ai.provider.name` (same) |
| `gen_ai.request.model` | `gen_ai.request.model` (same) |
| `gen_ai.operation.name` (`"tts"`) | `gen_ai.operation.name = text_to_speech` |
| `gen_ai.output.type` (`"speech"`) | `gen_ai.output.type = speech` (same) |
| `voice_id` | `gen_ai.speech.voice` |
| `text` | recorded as input message content |
| `tts.interrupted` (`True`) | `gen_ai.agent.invocation.end_reason = interrupted` (on the turn) |
| `metrics.ttfb` | — (voice latency; no stable `gen_ai.*` attribute yet) |
| `metrics.character_count`, `settings.*` | — (character billing / per-service detail) |

**`llm` span attributes** → `chat`

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `gen_ai.provider.name` | `gen_ai.provider.name` (same) |
| `gen_ai.request.model` | `gen_ai.request.model` (same) |
| `gen_ai.operation.name` (`"chat"`) | `gen_ai.operation.name = chat` (same) |
| `gen_ai.output.type` (`"text"`) | `gen_ai.output.type = text` (same) |
| `gen_ai.system_instructions` | `gen_ai.system_instructions` (same) |
| `gen_ai.request.temperature` / `max_tokens` / `max_completion_tokens` / `top_p` / `top_k` / `frequency_penalty` / `presence_penalty` / `seed` | same keys (reused verbatim) |
| `gen_ai.usage.input_tokens` / `output_tokens` | same keys (reused verbatim) |
| `gen_ai.usage.cache_read.input_tokens` / `cache_creation.input_tokens` / `reasoning_tokens` | — (cache / reasoning token breakdown; not in the GenAI registry) |
| `input` (JSON messages) | recorded as input message content |
| `output` (accumulated text) | recorded as output message content |
| `tools` / `tool_count` | tool definitions (recorded as message/tool content) |
| `stream` (`True`) | `gen_ai.request.stream` (equivalent; Pipecat uses a flat key) |
| `metrics.ttfb` | — (latency; no stable `gen_ai.*` attribute yet) |
| `param.*`, `extra.*` | — (unmapped per-service request params) |

Realtime spans (Gemini Live, OpenAI Realtime) largely duplicate the audio-token
and turn-completion signals of the dedicated realtime provider APIs surveyed
below, but through Pipecat-specific keys (`tokens.prompt` / `tokens.completion` /
`tokens.total` alongside `gen_ai.usage.input_tokens` / `output_tokens`,
`turn_complete`, `response.status`, `output_modality`). These map to
`gen_ai.usage.*`, `gen_ai.agent.invocation.end_reason`, and `gen_ai.output.type`
the same way as the [Gemini Live](#google-gemini-live) and
[Azure Voice Live](#azure-voice-live) tables.

### LiveKit Agents

- **Tracing**: deep native OpenTelemetry — traces, OTel metrics (histograms +
  counters), and structured logging under
  `livekit-agents/livekit/agents/telemetry/`.
- **Span hierarchy**: `agent_session` → `user_turn` (→ `eou_detection`) and
  `agent_turn` (→ `llm_node` → `llm_request`, `tts_node` → `tts_request`). User
  and agent turns are siblings, not one container.
- **Reuses `gen_ai.*`** including, notably,
  **`gen_ai.usage.input_audio_tokens` / `gen_ai.usage.output_audio_tokens`**
  — explicitly annotated in `trace_types.py` as "Unofficial OpenTelemetry GenAI
  attributes … not yet in the official OpenTelemetry specification." Also uses
  `gen_ai.usage.input_text_tokens` / `output_text_tokens` /
  `input_cached_tokens`.
- **Voice-specific fields** (LiveKit `lk.*` namespace): `lk.user_transcript`,
  `lk.transcript_confidence`, `lk.tts.label`, `lk.eou.language`,
  `lk.eou.probability`, `lk.interrupted`, `lk.is_interruption`,
  `lk.interruption.probability`, `lk.e2e_latency`, `lk.response.ttft`,
  `lk.response.ttfb`, `lk.transcription_delay`, `lk.speech_id`,
  `lk.generation_id`.
- **Barge-in**: multi-layered — VAD plus an adaptive ML interruption detector
  with probability, backchannel detection, and dedicated `InterruptionMetrics`.
- **Usage metrics**: OTel counters `lk.agents.usage.llm_input_audio_tokens`,
  `llm_output_audio_tokens`, `stt_audio_duration`, `tts_audio_duration`,
  `llm_session_duration`.
- **Realtime**: first-class; a `RealtimeModelMetrics` type with per-modality
  audio/text token details and TTFT = time to first audio.

**Span mapping**

| LiveKit span | `gen_ai.*` span / operation |
|---|---|
| `agent_session` | not a span — session correlation via `gen_ai.conversation.id` |
| `agent_turn` | `invoke_agent` (per-turn container over the response stages) |
| `user_turn` | input side of the turn (audio recorded as message parts on the turn's inference span) |
| `llm_node` / `llm_request` | `chat` |
| `tts_node` / `tts_request` | `gen_ai.text_to_speech.client` (`text_to_speech`) |
| (STT node) | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `eou_detection` | — (endpointing; provider-specific) |

LiveKit splits a single exchange into sibling `user_turn` and `agent_turn`
spans under a long-lived `agent_session`. The `agent_turn` span (nesting
`llm_node` / `tts_node`) is the closest match to the `invoke_agent` per-turn
container; `agent_session` spans the whole conversation and maps to the
`gen_ai.conversation.id` correlation attribute, not a span.

**Attribute mapping**

| LiveKit attribute | `gen_ai.*` attribute |
|---|---|
| `gen_ai.usage.input_audio_tokens` / `output_audio_tokens` | `gen_ai.usage.input_audio_tokens` / `output_audio_tokens` (verbatim) |
| `gen_ai.usage.input_text_tokens` / `output_text_tokens` | — (text/audio token split; not yet in spec) |
| `input_cached_tokens` | — (cached tokens; no dedicated attribute) |
| `lk.user_transcript` | recorded as transcript message content |
| `lk.tts.label` | `gen_ai.speech.voice` (approx) |
| `lk.eou.language` | `gen_ai.speech.input.language` |
| `lk.interrupted` / `lk.is_interruption` | `gen_ai.agent.invocation.end_reason = interrupted` |
| `lk.transcript_confidence` | — (proposed opt-in STT confidence; not yet in spec) |
| `lk.eou.probability`, `lk.interruption.probability` | — (endpointing / interruption ML; provider-specific) |
| `lk.e2e_latency`, `lk.response.ttft` / `ttfb`, `lk.transcription_delay` | — (voice latency; no stable `gen_ai.*` attribute yet) |
| `lk.speech_id`, `lk.generation_id` | — (provider-specific correlation ids) |

## Realtime (voice-native) provider APIs

### Google Gemini Live

- **Protocol**: stateful WebSocket (`BidiGenerateContent`).
- **Turn / interruption**: `BidiGenerateContentServerContent` carries booleans
  `turnComplete`, `generationComplete` (natural end), and `interrupted`
  (barge-in). On interruption, pending tool calls are cancelled via
  `BidiGenerateContentToolCallCancellation`. `goAway` warns of disconnect.
- **Audio tokens**: `usageMetadata` with `promptTokensDetails[]` /
  `responseTokensDetails[]` as arrays of
  `ModalityTokenCount{modality: AUDIO|TEXT|…, tokenCount}`.
- **Transcripts**: `inputTranscription.text` / `outputTranscription.text`.
- **Voice**: `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`.
- **Latency**: no server-emitted first-audio signal.

Gemini Live emits no OpenTelemetry spans; the tables show how its API concepts
would map.

**Span mapping**

| Gemini Live concept | `gen_ai.*` span / operation |
|---|---|
| Live session (`BidiGenerateContent`) | not a span — session correlation via `gen_ai.conversation.id` |
| turn (user utterance + model response cycle) | `invoke_agent` (per-turn container) |
| model response (server content until `turnComplete`) | `chat` (inference) |
| tool call (`toolCall`) | `execute_tool` |

**Attribute mapping**

| Gemini Live field | `gen_ai.*` attribute |
|---|---|
| model name | `gen_ai.request.model` |
| `promptTokensDetails[AUDIO].tokenCount` | `gen_ai.usage.input_audio_tokens` |
| `responseTokensDetails[AUDIO].tokenCount` | `gen_ai.usage.output_audio_tokens` |
| total prompt / response token counts | `gen_ai.usage.input_tokens` / `output_tokens` |
| `promptTokensDetails[TEXT]` / `responseTokensDetails[TEXT]` | — (text/audio token split; not yet in spec) |
| `turnComplete` / `generationComplete` | `gen_ai.agent.invocation.end_reason = completed` |
| `interrupted` | `gen_ai.agent.invocation.end_reason = interrupted` |
| `goAway` (disconnect) | `gen_ai.agent.invocation.end_reason = session_closed` |
| `inputTranscription.text` / `outputTranscription.text` | recorded as transcript message content |
| `speechConfig…voiceName` | `gen_ai.speech.voice` |
| declared language code | `gen_ai.speech.input.language` |

### Azure Voice Live

- **Protocol**: stateful WebSocket following the OpenAI Realtime API spec, with
  Azure extensions (semantic VAD, Azure voices, avatar).
- **Turn / interruption**: turn = `response.created` → `response.done`. The
  `response.status` enum is `in_progress` / `completed` / `canceled`
  (client `response.cancel`) / `incomplete` (VAD barge-in) / `failed`. VAD emits
  `input_audio_buffer.speech_started` / `speech_stopped`.
- **Audio tokens**: `response.usage.input_token_details.{audio_tokens,text_tokens,cached_tokens}`
  and `output_token_details.{audio_tokens,text_tokens}` (flat sub-fields).
- **Transcripts**: `conversation.item.input_audio_transcription.completed`
  (input) and `response.audio_transcript.done` (output).
- **Voice / audio**: `voice` (discriminated union: `openai` / `azure-standard` /
  `azure-custom` / `azure-personal`, with `name`, `style`, `pitch`, `rate`);
  `input_audio_format` / `output_audio_format` / `input_audio_sampling_rate`.
- **Latency**: word-level `response.audio_timestamp.delta` (`audio_offset_ms`);
  the first event approximates time-to-first-audio from `response.created`.

Partial OpenTelemetry exists via OpenLLMetry's OpenAI Realtime wrappers; the
tables reflect that mapping plus the remaining API fields.

**Span mapping**

| Azure Voice Live concept | `gen_ai.*` span / operation |
|---|---|
| realtime session | not a span — session correlation via `gen_ai.conversation.id` |
| turn (user utterance + its response(s)) | `invoke_agent` (per-turn container) |
| `response.created` → `response.done` (one model response) | `chat` (inference) |
| function / tool call | `execute_tool` |

Note: OpenLLMetry's existing wrappers currently place a single `invoke_agent`
span at the *session* level rather than per turn — a divergence from the per-turn
container these conventions specify.

**Attribute mapping**

| Azure Voice Live field | `gen_ai.*` attribute |
|---|---|
| `response.usage.input_token_details.audio_tokens` | `gen_ai.usage.input_audio_tokens` |
| `response.usage.output_token_details.audio_tokens` | `gen_ai.usage.output_audio_tokens` |
| `…input_token_details.text_tokens` / `output_token_details.text_tokens` | — (text/audio token split; not yet in spec) |
| `…input_token_details.cached_tokens` | — (cached tokens; no dedicated attribute) |
| total usage tokens | `gen_ai.usage.input_tokens` / `output_tokens` |
| `response.status = completed` | `gen_ai.agent.invocation.end_reason = completed` |
| `response.status = incomplete` (VAD barge-in) | `gen_ai.agent.invocation.end_reason = interrupted` |
| `response.status = canceled` (client cancel) | `gen_ai.agent.invocation.end_reason = interrupted` (cancel vs barge-in not distinguished — see open questions) |
| `response.status = failed` | span status `Error` + `error.type` (failures are not an end-reason value) |
| `voice.name` | `gen_ai.speech.voice` |
| input-audio transcription language | `gen_ai.speech.input.language` |
| `input_audio_format` / `output_audio_format` / `input_audio_sampling_rate` | — (provider-specific audio format) |

## Dedicated STT / TTS providers

### Deepgram

- **STT** (`POST /v1/listen`): `metadata.duration` (audio seconds),
  `detected_language` (BCP-47, when `detect_language=true`),
  `alternatives[].confidence` (overall 0–1) and `words[].confidence` (per-word).
  Streaming adds `is_final` / `speech_final`, `SpeechStarted`, `UtteranceEnd`,
  and `endpointing`.
- **TTS** (`POST /v1/speak`): voice + language are encoded in the single `model`
  parameter (`aura-2-thalia-en`); no separate `voice_id`. Format via `encoding` +
  `sample_rate` + `container`. Response is raw audio (no usage body).
- **Billing**: duration-based (audio seconds) for STT; no token concept.

**Span mapping**

| Deepgram operation | `gen_ai.*` span / operation |
|---|---|
| `POST /v1/listen` (STT) | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `POST /v1/speak` (TTS) | `gen_ai.text_to_speech.client` (`text_to_speech`) |

**Attribute mapping**

| Deepgram field | `gen_ai.*` attribute |
|---|---|
| `model` | `gen_ai.request.model` |
| `detected_language` | `gen_ai.speech.input.language` |
| TTS voice (encoded in `model`, e.g. `aura-2-thalia-en`) | `gen_ai.speech.voice` (or via model) |
| `alternatives[].confidence` | — (proposed opt-in STT confidence; not yet in spec) |
| `metadata.duration` (audio seconds) | — (proposed audio-duration usage; not yet in spec) |
| `words[].confidence`, `is_final` / `speech_final`, `endpointing` | — (per-word / streaming detail) |
| `encoding` / `sample_rate` / `container` | — (provider-specific audio format) |

### ElevenLabs

- **STT** (`POST /v1/speech-to-text`): always returns `language_code`
  (ISO-639-3) and `language_probability` (language-detection confidence 0–1),
  `audio_duration_secs`, and per-word `logprob` (no overall confidence). Batch
  only — realtime STT exists only inside the Conversational AI product.
- **TTS** (`POST /v1/text-to-speech/{voice_id}`): opaque `voice_id` (path) plus a
  separate human-readable `voice_name` (history), `model_id` distinct from voice,
  combined `output_format` (`mp3_44100_128`), and `optimize_streaming_latency`
  (0–4). Billing is character-based (`character_count_change_*`).
- **Conversational AI**: documented 4-stage architecture (STT → LLM → TTS +
  turn-taking model) with a WebSocket protocol (`user_transcript`,
  `agent_response`, `audio`, `interruption`, `ping`). Analytics are dashboard
  only (agent response latency, turn-taking latency p50/p90/p99, LLM time to
  first sentence) — no OpenTelemetry export.

**Span mapping**

| ElevenLabs operation | `gen_ai.*` span / operation |
|---|---|
| `POST /v1/speech-to-text` | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `POST /v1/text-to-speech/{voice_id}` | `gen_ai.text_to_speech.client` (`text_to_speech`) |
| Conversational AI pipeline (STT → LLM → TTS) | `invoke_agent` over `speech_to_text` / `chat` / `text_to_speech` |

**Attribute mapping**

| ElevenLabs field | `gen_ai.*` attribute |
|---|---|
| `model_id` | `gen_ai.request.model` |
| `voice_id` / `voice_name` | `gen_ai.speech.voice` |
| `language_code` | `gen_ai.speech.input.language` |
| ConvAI `interruption` | `gen_ai.agent.invocation.end_reason = interrupted` |
| `language_probability` | — (language-detection confidence; provider-specific / opt-in) |
| `audio_duration_secs` | — (proposed audio-duration usage; not yet in spec) |
| per-word `logprob` | — (no overall confidence; provider-specific) |
| `output_format`, `optimize_streaming_latency` | — (provider-specific audio / latency knob) |
| `character_count_change_*` | — (character-based billing; provider-specific) |

## Mapping to the proposed conventions

**Confirmed by the survey:**

- **Audio-token attributes** (`gen_ai.usage.input_audio_tokens` /
  `output_audio_tokens`) — LiveKit already emits them verbatim; Azure Voice Live
  and Gemini Live both report the underlying per-modality audio token counts.
- **`invoke_agent` as the agent turn container** — Pipecat's `turn` span and
  LiveKit's `agent_turn` span both act as the per-exchange container over the
  stage spans, matching the role these conventions give `invoke_agent`.
  OpenLLMetry's OpenAI Realtime instrumentation also uses
  `gen_ai.operation.name = invoke_agent`, though at the session scope rather than
  per turn (see the [Azure Voice Live](#azure-voice-live) note).
- **Session correlation via `gen_ai.conversation.id`** — the long-lived session
  span in Pipecat (`conversation`), LiveKit (`agent_session`), and the realtime
  provider sessions is a correlation concept, mapped to `gen_ai.conversation.id`
  rather than a dedicated span.
- **`speech_to_text` / `text_to_speech` operations** — match Pipecat's `stt` /
  `tts` operation values.
- **User audio as message parts (no dedicated user span)** — consistent with how
  all surveyed libraries stream input audio. The audio may be inlined as a `blob`
  part or stored by reference as a `uri` / `file` part (see
  [Audio content and transcripts](../gen-ai-voice-agents.md#audio-content-and-transcripts)),
  which matters for voice, where audio payloads are large and usually stored
  externally rather than on the span.

**Changes / additions the survey motivates:**

- **`gen_ai.agent.invocation.end_reason` replaces the earlier
  `gen_ai.conversation.turn.end_reason`.** Because `invoke_agent` is the per-turn
  container, the end reason is modeled as a general agent-invocation outcome set
  on that span rather than as a voice/turn-specific attribute. This generalizes
  beyond voice to any agent invocation and matches the flat `end_reason` used by
  Arize OpenInference and the `response.status` field of OpenAI / Azure Realtime.
  Failures are represented by span status `Error` + `error.type` (not an
  end-reason value), which is why the enum (`completed` / `interrupted` /
  `session_closed`) omits `failed`. Client-cancel and barge-in are both mapped to
  `interrupted`; distinguishing them remains an open question.
- **STT transcription confidence** is real (Deepgram `confidence`, LiveKit
  `lk.transcript_confidence`) but not universal (ElevenLabs has per-word `logprob`
  only) — suitable as an Opt-In attribute.
- **Audio duration is the natural STT / TTS usage unit** (Deepgram
  `metadata.duration`, ElevenLabs `audio_duration_secs`, LiveKit audio-duration
  counters); dedicated STT / TTS providers have no token concept.
- **Text vs audio token split** — LiveKit, Azure, and Gemini all report text
  tokens alongside audio tokens.
- **Voice id vs name is ambiguous** — ElevenLabs opaque `voice_id` + separate
  `voice_name`; Deepgram encodes voice in `model`; Gemini / Azure use `voice.name`.
- **Declared vs detected input language** are distinct fields in Deepgram and
  ElevenLabs; `gen_ai.speech.input.language` currently conflates them.
- **Perceived / end-to-end latency** is a first-class ecosystem metric (LiveKit
  `lk.e2e_latency`, ElevenLabs turn-taking latency), supporting a dedicated voice
  latency signal over reusing `gen_ai.response.time_to_first_chunk`.

**Likely provider-specific** (probably out of scope for generic `gen_ai.*`):
end-of-utterance / endpointing models, backchannel detection, VAD / turn-detection
type, audio format / sample rate, TTS character count, diarization speaker counts,
Gemini thinking tokens, word-level audio timestamps.

## Whole-conversation audio and session modeling

Two related questions came up while validating the conventions against real
traces: (1) how is the audio for an entire conversation referenced, and (2)
should a voice conversation be modeled as a long-lived span. The survey below
records the evidence and the resulting decisions.

### How prior art references whole-conversation audio

No surveyed tracing instrumentation references the audio for an entire
conversation as a single artifact **in the trace**. Where whole-conversation
audio exists, it lives in a product data model or a separate recording feature,
correlated back to the trace (at best) by a conversation identifier. Four
concrete sample traces and the corresponding framework mechanisms:

| Source | Whole-conversation audio? | Where it lives | In the trace? |
| --- | --- | --- | --- |
| **ElevenLabs ConvAI** | Yes — recorded automatically, server-side, one recording per conversation (`GET /v1/convai/conversations/{conversation_id}/audio`). User and agent audio are retained distinctly (`has_user_audio` / `has_response_audio`), but the public download returns a single combined recording. | ElevenLabs platform, keyed by `conversation_id`. | No. The trace/export carries only `conversation_id`; audio is fetched out of band. |
| **Pipecat** | Yes, if the pipeline includes an [`AudioBufferProcessor`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/processors/audio/audio_buffer_processor.py). It time-aligns both directions and emits the whole conversation via `on_audio_data` (merged; mono mix, or stereo with user-left / bot-right) and `on_track_audio_data` (separate user / bot tracks). | Wherever the application writes it (local file, object storage). Storage is not built in. | No, and there is no built-in identifier linking the recording to the span. |
| **OpenAI Agents SDK** | No whole-conversation file. Audio appears per span as inline base64 PCM — user audio on the `TranscriptionSpanData` `input`, agent audio on the `SpeechSpanData` `output` — gated behind `trace_include_sensitive_audio_data` (often empty). | Inline in the trace, per utterance. | Per-span only, never assembled into one conversation artifact. |
| **Microsoft Pipecat cascade sample** | No audio at all. Transcripts and voice metadata (`voice_id`, `gen_ai.output.type = speech`) only. | — | No audio references of any kind. |

Whole-call single recordings also exist outside traces in `Vapi`
(`stereoRecordingUrl`), `Retell` (`recording_multi_channel_url`), LiveKit
Egress (a single composite file), and Twilio (`RecordingUrl`) — all delivered
via webhooks / data models at call end, never attached to OTel spans. Several
support a multi-channel (per-speaker) layout, matching the ElevenLabs
`has_user_audio` / `has_response_audio` split and Pipecat's `on_track_audio_data`
tracks.

**Takeaway:** the audio (and often a per-speaker split) exists almost
everywhere; the missing piece is a portable, in-trace reference. A
conversation-scoped recording reference — a `uri` / `file_id` plus a `channels[]`
layout (index → role, e.g. `0 = user`, `1 = assistant`) and duration, correlated
by `gen_ai.conversation.id` — would make it interoperable without embedding large
audio payloads on spans. This remains an open proposal.

### Conversation is modeled as an id, not a span

A voice conversation is **not** modeled as a span. It is correlated across the
per-turn `invoke_agent` spans by the `gen_ai.conversation.id` attribute, matching
the rest of the GenAI conventions (which never model a conversation as a span)
and the Arize OpenInference approach (a `session.id` attribute rather than a
session span). This diverges from most other prior art — OpenLLMetry
("Realtime Session"), Pipecat (`conversation`), LiveKit (`agent_session`), and
Hamming (`call.lifecycle`) each open a session-level span — but the divergence is
deliberate:

- **Long-lived spans are an anti-pattern here.** A voice call runs for minutes to
  hours, and a span is exported only when it ends. A conversation span therefore
  yields no telemetry until the call finishes, retains an open span in memory for
  the whole call, and is **lost entirely if the process crashes or the WebSocket
  drops** — a common failure mode for long-lived realtime connections.
- **A conversation is not one bounded operation in one trace.** It can survive
  reconnects, span multiple processes or load-balanced realtime backends, and
  naturally decomposes into one trace per turn. That is a logical cross-cutting
  grouping, which a correlation id expresses well and a span expresses poorly.
- **The transport is untraced.** There is no finalized OpenTelemetry semantic
  convention for WebSocket connections (the handshake is covered by HTTP
  conventions; frames, messages, and close codes are not) and no portable
  connection identifier, so there is no transport boundary to anchor a
  conversation span to. `gen_ai.conversation.id` is the only stable join key.

**Recovering session-level semantics without a session span.** The benefits a
session span would provide — a place to hang whole-conversation data such as the
audio recording reference, total durations / token counts, and a session-level
outcome — can instead be carried by a **conversation-scoped event emitted at
session end** (for example `gen_ai.conversation.details`), correlated by
`gen_ai.conversation.id`. Such an event is exported at end like any other event,
holds nothing open for the duration of the call, survives the per-turn trace
model, and lets consumers reconstruct the conversation by grouping on
`gen_ai.conversation.id` (exactly how ElevenLabs' `conversation_id` and Arize's
`session.id` are used today). Defining that event is an open proposal.

## Open questions

The following are unresolved and the most likely to change before
stabilization. They are recorded here as options, without a recommendation.

### Conversation modeling: session span vs. id + session-end event

How a voice conversation (a session spanning many turns) should be modeled is
open. Two approaches:

**Approach 1 — model the conversation as a long-lived span.** A single
`conversation` / `agent_session` span is opened at session start and closed at
session end, with the per-turn `invoke_agent` spans as its children. This is what
most surveyed prior art does (OpenLLMetry "Realtime Session", Pipecat
`conversation`, LiveKit `agent_session`, Hamming `call.lifecycle`).

- *For:* one natural place to hang whole-conversation data (audio recording
  reference, total durations / token counts, session-level outcome); a single
  trace that visually contains the whole call; matches most existing voice-agent
  instrumentation.
- *Against:* a span is exported only when it ends, so there is no telemetry until
  the call finishes and the span is lost entirely if the process crashes or the
  WebSocket drops (a common realtime failure mode); a conversation is not one
  bounded operation — it can survive reconnects, span multiple processes or
  load-balanced backends, and naturally decomposes into one trace per turn; the
  transport has no finalized OTel convention or portable connection id to anchor
  the span to.

**Approach 2 — model the conversation as an id plus a session-end event.** No
conversation span. The turns are correlated by the `gen_ai.conversation.id`
attribute on each `invoke_agent` span, and the session-level data a span would
have carried is emitted as a conversation-scoped event at session end (for
example `gen_ai.conversation.details`), also correlated by
`gen_ai.conversation.id`. This is the approach described under
[Whole-conversation audio and session modeling](#whole-conversation-audio-and-session-modeling);
it matches the rest of the GenAI conventions (which never model a conversation as
a span) and Arize OpenInference (`session.id` attribute, not a span).

- *For:* nothing is held open for the call duration; data is exported
  incrementally (per turn) and at session end, surviving crashes and reconnects;
  works across processes and per-turn traces; needs only a stable join key, which
  `gen_ai.conversation.id` already provides.
- *Against:* diverges from most existing voice instrumentation; consumers must
  reconstruct the session by grouping on `gen_ai.conversation.id` rather than
  reading one span tree; the session-end event (`gen_ai.conversation.details`) is
  not yet defined.

|  | Approach 1: session span | Approach 2: id + session-end event |
| --- | --- | --- |
| Session-level data home | span attributes | session-end event |
| Turn correlation | parent span | `gen_ai.conversation.id` |
| Survives crash / WS drop | no (span lost) | yes (per-turn + end event) |
| Telemetry before call ends | no | yes (per turn) |
| Multi-process / reconnect | poor fit | natural |
| Ecosystem alignment | matches most prior art | matches GenAI conventions + Arize |

### Other open questions

- **Barge-in vs. client cancel.** A user interruption (barge-in) and a
  programmatic cancel both map to `gen_ai.agent.invocation.end_reason =
  interrupted` (and both appear as `response.status = canceled` in OpenAI /
  Azure Realtime). Whether to distinguish them is open.
- **STT transcription confidence.** Real (Deepgram `confidence`, LiveKit
  `lk.transcript_confidence`) but not universal (ElevenLabs exposes per-word
  `logprob` only). Candidate as an Opt-In attribute; not yet in spec.
- **Audio duration as the STT / TTS usage unit.** Dedicated speech providers have
  no token concept and bill by audio duration (Deepgram `metadata.duration`,
  ElevenLabs `audio_duration_secs`, LiveKit audio-duration counters). Whether to
  add a duration-based usage measure is open.
- **Text vs. audio token split.** LiveKit, Azure Voice Live, and Gemini Live all
  report text tokens alongside audio tokens. Whether to add
  `gen_ai.usage.input_text_tokens` / `output_text_tokens` is open.
- **Voice id vs. name.** Providers disagree: ElevenLabs uses an opaque `voice_id`
  plus a separate `voice_name`, Deepgram encodes the voice in `model`, and
  Gemini / Azure use `voice.name`. How `gen_ai.speech.voice` should represent this
  is open.
- **Declared vs. detected input language.** Deepgram and ElevenLabs treat the
  requested language and the detected language as distinct fields;
  `gen_ai.speech.input.language` currently conflates them.
- **Perceived / end-to-end latency.** A first-class ecosystem metric (LiveKit
  `lk.e2e_latency`, ElevenLabs turn-taking latency). Whether to define a dedicated
  voice-latency signal or reuse `gen_ai.response.time_to_first_chunk` is open.
- **Whole-conversation audio reference.** A portable, in-trace reference to the
  whole-conversation recording — a `uri` / `file_id` plus a `channels[]` layout
  (index → role) and duration, correlated by `gen_ai.conversation.id` — does not
  exist in any surveyed instrumentation. Whether to define one is open.
- **Provider-specific attributes.** End-of-utterance / endpointing models,
  backchannel detection, VAD / turn-detection type, audio format / sample rate,
  TTS character count, diarization speaker counts, Gemini thinking tokens, and
  word-level audio timestamps are likely out of scope for generic `gen_ai.*`, but
  this boundary is not settled.

## Instrumentation gaps

There is currently no published OpenTelemetry instrumentation for Deepgram,
ElevenLabs, or Google Gemini Live (`aio.live`), and only partial coverage for
Azure Voice Live (via OpenLLMetry's OpenAI Realtime wrappers, which omit audio
token details, response status, interruption, and voice config). These
conventions would fill a real, unserved gap rather than compete with an
established practice.

## References

- OpenAI Agents voice pipeline: <https://github.com/openai/openai-agents-python/pull/265>
- Arize OpenInference realtime audio tracing: <https://github.com/Arize-ai/openinference/pull/3173>
- Hamming voice-agent OpenTelemetry guide: <https://hamming.ai/resources/opentelemetry-voice-agents-tracing-guide>
- Pipecat tracing: `pipecat-ai/pipecat` — `src/pipecat/utils/tracing/`
- Pipecat audio recording: `pipecat-ai/pipecat` — `src/pipecat/processors/audio/audio_buffer_processor.py`
- OpenAI Agents SDK trace span data (audio inline on speech / transcription spans): `openai/openai-agents-python` — `src/agents/tracing/span_data.py`
- LiveKit Agents telemetry: `livekit/agents` — `livekit-agents/livekit/agents/telemetry/trace_types.py`
- Google Gemini Live API reference: <https://ai.google.dev/api/live>
- Azure Voice Live API reference (2025-10-01): <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-api-reference-2025-10-01>
- OpenLLMetry OpenAI Realtime instrumentation: `traceloop/openllmetry` — `packages/opentelemetry-instrumentation-openai/opentelemetry/instrumentation/openai/v1/realtime_wrappers.py`
- Deepgram STT / TTS API: <https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded>
- ElevenLabs STT / TTS API: <https://elevenlabs.io/docs/api-reference/speech-to-text/convert>
- ElevenLabs ConvAI conversation audio (single recording per conversation): <https://elevenlabs.io/docs/api-reference/conversations/get-audio>

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
