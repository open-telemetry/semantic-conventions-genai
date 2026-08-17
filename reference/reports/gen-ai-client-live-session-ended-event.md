# Live Session Ended Event

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [gemini-live], [gemini-live-3], [openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [openai-realtime] |
| gen_ai.request.model | [gemini-live], [gemini-live-3], [openai-realtime] |
| server.port | [gemini-live], [gemini-live-3], [openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [gemini-live], [gemini-live-3], [openai-realtime] |

[gemini-live]: ../scenarios/gemini-live/scenario.py
[gemini-live-3]: ../scenarios/gemini-live-3/scenario.py
[openai-realtime]: ../scenarios/openai-realtime/scenario.py
