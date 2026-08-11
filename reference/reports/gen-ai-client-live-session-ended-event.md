# Live Session Ended Event

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [gemini-live], [openai-realtime] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.conversation.id | [openai-realtime] |
| gen_ai.request.model | [gemini-live], [openai-realtime] |
| server.port | [gemini-live], [openai-realtime] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [gemini-live], [openai-realtime] |

[gemini-live]: ../scenarios/gemini-live/scenario.py
[openai-realtime]: ../scenarios/openai-realtime/scenario.py
