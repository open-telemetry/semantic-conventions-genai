# Embeddings Span

> **[Semantic Convention](../../docs/gen-ai/gen-ai-spans.md#embeddings)**

## Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.operation.name | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [openai] |
| gen_ai.provider.name | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [openai] |

## Conditionally Required

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.request.model | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [google-genai], [litellm], [mistralai], [openai] |
| server.port | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [mistralai], [openai] |

## Recommended

| Attribute | Supporting Libraries |
| --- | --- |
| gen_ai.embeddings.dimension.count | [azure-openai], [google-genai], [openai] |
| gen_ai.request.encoding_formats | [azure-openai], [openai] |
| gen_ai.response.model | [azure-ai-inference], [azure-openai], [litellm], [mistralai], [openai] |
| gen_ai.usage.input_tokens | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [litellm], [mistralai], [openai] |
| server.address | [aws-bedrock], [azure-ai-inference], [azure-openai], [cohere], [mistralai], [openai] |

[aws-bedrock]: ../scenarios/aws-bedrock/scenario.py
[azure-ai-inference]: ../scenarios/azure-ai-inference/scenario.py
[azure-openai]: ../scenarios/azure-openai/scenario.py
[cohere]: ../scenarios/cohere/scenario.py
[google-genai]: ../scenarios/google-genai/scenario.py
[litellm]: ../scenarios/litellm/scenario.py
[mistralai]: ../scenarios/mistralai/scenario.py
[openai]: ../scenarios/openai/scenario.py
