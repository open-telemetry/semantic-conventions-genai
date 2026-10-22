# Evaluation Result Event

> **[Semantic Convention](../../docs/gen-ai/gen-ai-events.md#event-gen_aievaluationresult)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.name | [aws-bedrock-agentcore], [azure-ai-evaluation], [deepeval], [dspy] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.score.label | [aws-bedrock-agentcore], [azure-ai-evaluation], [dspy] |
| gen_ai.evaluation.score.value | [aws-bedrock-agentcore], [azure-ai-evaluation], [deepeval], [dspy] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.evaluation.explanation | [aws-bedrock-agentcore], [azure-ai-evaluation], [deepeval] |
| gen_ai.evaluation.score.direction | [azure-ai-evaluation] |
| gen_ai.evaluation.score.rating_scale | [aws-bedrock-agentcore] |
| gen_ai.response.id | (none) |

[aws-bedrock-agentcore]: ../scenarios/aws-bedrock-agentcore/scenario.py
[azure-ai-evaluation]: ../scenarios/azure-ai-evaluation/scenario.py
[deepeval]: ../scenarios/deepeval/scenario.py
[dspy]: ../scenarios/dspy/scenario.py
