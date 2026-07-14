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
| `conversation` (tracer `pipecat.turn`) | `invoke_agent` (agent session container) |
| `turn` (tracer `pipecat.turn`) | conversation turn (no dedicated span; `gen_ai.conversation.turn.*`) |
| `stt` | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `llm` | `chat` |
| `tts` | `gen_ai.text_to_speech.client` (`text_to_speech`) |
| realtime `llm_setup` / `llm_request` / `llm_response` / `llm_tool_call` / `llm_tool_result` (Gemini Live, OpenAI Realtime) | conversation turn under `invoke_agent`; tool ops → `execute_tool` |

**`conversation` span attributes**

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `conversation.id` | `gen_ai.conversation.id` |
| `conversation.type` (`"voice"`) | — (no `gen_ai.*` equivalent) |
| `additional_span_attributes.*` | — (user-supplied resource/context) |

**`turn` span attributes**

| Pipecat attribute | `gen_ai.*` attribute |
|---|---|
| `turn.was_interrupted` (`True`) | `gen_ai.conversation.turn.end_reason = interrupted` |
| `turn.ended_by_conversation_end` (`True`) | `gen_ai.conversation.turn.end_reason = session_closed` |
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
| `tts.interrupted` (`True`) | `gen_ai.conversation.turn.end_reason = interrupted` (on the turn) |
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
`gen_ai.usage.*`, `gen_ai.conversation.turn.end_reason`, and `gen_ai.output.type`
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
| `agent_session` | `invoke_agent` (session container) |
| `user_turn` | conversation turn, input side (`gen_ai.conversation.turn.*`) |
| `agent_turn` | conversation turn, response side |
| `llm_node` / `llm_request` | `chat` |
| `tts_node` / `tts_request` | `gen_ai.text_to_speech.client` (`text_to_speech`) |
| (STT node) | `gen_ai.speech_to_text.client` (`speech_to_text`) |
| `eou_detection` | — (endpointing; provider-specific) |

**Attribute mapping**

| LiveKit attribute | `gen_ai.*` attribute |
|---|---|
| `gen_ai.usage.input_audio_tokens` / `output_audio_tokens` | `gen_ai.usage.input_audio_tokens` / `output_audio_tokens` (verbatim) |
| `gen_ai.usage.input_text_tokens` / `output_text_tokens` | — (text/audio token split; not yet in spec) |
| `input_cached_tokens` | — (cached tokens; no dedicated attribute) |
| `lk.user_transcript` | recorded as transcript message content |
| `lk.tts.label` | `gen_ai.speech.voice` (approx) |
| `lk.eou.language` | `gen_ai.speech.input.language` |
| `lk.interrupted` / `lk.is_interruption` | `gen_ai.conversation.turn.end_reason = interrupted` |
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
| Live session (`BidiGenerateContent`) | `invoke_agent` (session container) |
| model turn (server content until `turnComplete`) | conversation turn |
| tool call (`toolCall`) | `execute_tool` |

**Attribute mapping**

| Gemini Live field | `gen_ai.*` attribute |
|---|---|
| model name | `gen_ai.request.model` |
| `promptTokensDetails[AUDIO].tokenCount` | `gen_ai.usage.input_audio_tokens` |
| `responseTokensDetails[AUDIO].tokenCount` | `gen_ai.usage.output_audio_tokens` |
| total prompt / response token counts | `gen_ai.usage.input_tokens` / `output_tokens` |
| `promptTokensDetails[TEXT]` / `responseTokensDetails[TEXT]` | — (text/audio token split; not yet in spec) |
| `turnComplete` / `generationComplete` | `gen_ai.conversation.turn.end_reason = complete` |
| `interrupted` | `gen_ai.conversation.turn.end_reason = interrupted` |
| `goAway` (disconnect) | `gen_ai.conversation.turn.end_reason = session_closed` |
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
| realtime session | `invoke_agent` (OpenLLMetry uses `gen_ai.operation.name = invoke_agent`) |
| `response.created` → `response.done` | conversation turn |
| function / tool call | `execute_tool` |

**Attribute mapping**

| Azure Voice Live field | `gen_ai.*` attribute |
|---|---|
| `response.usage.input_token_details.audio_tokens` | `gen_ai.usage.input_audio_tokens` |
| `response.usage.output_token_details.audio_tokens` | `gen_ai.usage.output_audio_tokens` |
| `…input_token_details.text_tokens` / `output_token_details.text_tokens` | — (text/audio token split; not yet in spec) |
| `…input_token_details.cached_tokens` | — (cached tokens; no dedicated attribute) |
| total usage tokens | `gen_ai.usage.input_tokens` / `output_tokens` |
| `response.status = completed` | `gen_ai.conversation.turn.end_reason = complete` |
| `response.status = incomplete` (VAD barge-in) | `gen_ai.conversation.turn.end_reason = interrupted` |
| `response.status = canceled` (client cancel) | `gen_ai.conversation.turn.end_reason = interrupted` (cancel vs barge-in not distinguished — see open questions) |
| `response.status = failed` | — (no `failed` value yet; proposed addition) |
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
| ConvAI `interruption` | `gen_ai.conversation.turn.end_reason = interrupted` |
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
- **`invoke_agent` as the realtime turn container** — OpenLLMetry's OpenAI
  Realtime instrumentation independently uses
  `gen_ai.operation.name = invoke_agent` for agent sessions.
- **`speech_to_text` / `text_to_speech` operations** — match Pipecat's `stt` /
  `tts` operation values.
- **User audio as message parts (no dedicated user span)** — consistent with how
  all surveyed libraries stream input audio.

**Changes / additions the survey motivates:**

- **`gen_ai.conversation.turn.end_reason` needs more states.** Azure distinguishes
  `completed` / `canceled` (client) / `incomplete` (barge-in) / `failed`; the
  draft enum (`complete` / `interrupted` / `session_closed`) is missing `failed`
  and collapses client-cancel and barge-in.
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
- LiveKit Agents telemetry: `livekit/agents` — `livekit-agents/livekit/agents/telemetry/trace_types.py`
- Google Gemini Live API reference: <https://ai.google.dev/api/live>
- Azure Voice Live API reference (2025-10-01): <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-api-reference-2025-10-01>
- OpenLLMetry OpenAI Realtime instrumentation: `traceloop/openllmetry` — `packages/opentelemetry-instrumentation-openai/opentelemetry/instrumentation/openai/v1/realtime_wrappers.py`
- Deepgram STT / TTS API: <https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded>
- ElevenLabs STT / TTS API: <https://elevenlabs.io/docs/api-reference/speech-to-text/convert>

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
