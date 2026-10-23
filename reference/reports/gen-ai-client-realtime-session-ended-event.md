# Realtime Session Ended Event

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.provider.name | [google-genai], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.realtime_session.id | [openai] |
| gen_ai.request.model | [google-genai], [openai] |
| server.port | [google-genai], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| server.address | [google-genai], [openai] |

[google-genai]: ../scenarios/google-genai/scenario.py
[openai]: ../scenarios/openai/scenario.py
