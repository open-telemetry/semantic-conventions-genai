# Client Embeddings Duration Metric

> **[Semantic Convention](../../docs/gen-ai/client-embeddings.md#metric-gen_aiclientembeddingsduration)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [ollama], [openai] |
| gen_ai.provider.name | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [ollama], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [ollama], [openai] |
| server.port | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [litellm], [mistralai], [ollama], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.response.model | [azure-ai-inference], [azure-openai], [litellm], [mistralai], [ollama], [openai] |
| server.address | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [ollama], [openai] |

[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[ollama]: ../scenarios/ollama/scenario.py
[openai]: ../scenarios/openai/scenario.py
