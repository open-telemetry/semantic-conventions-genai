# Evaluation Result Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aievaluationresult)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.name | [azure-ai-evaluation], [deepeval], [dspy] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.score.label | [azure-ai-evaluation], [dspy] |
| gen_ai.evaluation.score.value | [azure-ai-evaluation], [deepeval], [dspy] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.explanation | [azure-ai-evaluation], [deepeval] |
| gen_ai.response.id | (none) |

[azure-ai-evaluation]: ../scenarios/azure-ai-evaluation/scenario.py
[deepeval]: ../scenarios/deepeval/scenario.py
[dspy]: ../scenarios/dspy/scenario.py
