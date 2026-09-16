# Client Inference Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-inference.md#metric-gen_aiclientinferenceduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [groq] |
| gen_ai.provider.name | [groq] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [groq] |
| server.port | [groq] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [groq] |
| server.address | [groq] |

[groq]: ../scenarios/groq/scenario.py
