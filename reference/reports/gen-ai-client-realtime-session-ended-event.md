# Realtime Session Ended Event

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.realtime_session.id | [openai][openai@openai-realtime] |
| gen_ai.request.model | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |
| server.port | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [google-genai][google-genai@gemini-live], [openai][openai@openai-realtime] |

[google-genai@gemini-live]: ../scenarios/gemini-live/scenario.py
[openai@openai-realtime]: ../scenarios/openai-realtime/scenario.py
