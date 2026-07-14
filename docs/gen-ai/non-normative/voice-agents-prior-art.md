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
