# Ollama Reference Scenario

This scenario demonstrates the use of [Ollama semantic conventions](../../../model/ollama/)
for tracing Ollama API calls.

## Overview

Ollama is an open-source platform for running large language models locally. This scenario
shows how to instrument Ollama API calls with OpenTelemetry semantic conventions.

## Running the Scenario

```bash
# From the repository root
cd reference/scenarios/ollama

# Install dependencies
uv sync

# Run the scenario
uv run python scenario.py
```

## What This Scenario Tests

This scenario creates spans for two Ollama operations:

1. **Chat Completion** (`ollama.client.chat`):
   - Uses the `/api/chat` endpoint
   - Includes request parameters: model, messages, temperature, top_p, max_tokens
   - Includes response attributes: model, total_duration, eval_count

2. **Text Generation** (`ollama.client.generate`):
   - Uses the `/api/generate` endpoint
   - Includes request parameters: model, prompt, temperature, max_tokens
   - Includes response attributes: model, total_duration, eval_count

## Expected Output

The scenario generates OpenTelemetry spans with the following Ollama-specific attributes:

### Request Attributes
- `ollama.request.model`: The model name (e.g., "llama3.2", "mistral")
- `ollama.request.base_url`: The Ollama API endpoint URL
- `ollama.request.stream`: Whether streaming is enabled
- `ollama.request.temperature`: Temperature setting
- `ollama.request.top_p`: Top-p sampling
- `ollama.request.max_tokens`: Maximum tokens to generate
- `ollama.request.stop`: Stop sequences
- `ollama.request.repeat_penalty`: Repeat penalty
- `ollama.request.seed`: Random seed

### Response Attributes
- `ollama.response.model`: The model that generated the response
- `ollama.response.total_duration`: Total time in nanoseconds
- `ollama.response.load_duration`: Model load time in nanoseconds
- `ollama.response.prompt_eval_count`: Number of prompt tokens evaluated
- `ollama.response.eval_count`: Number of tokens generated

## Generic GenAI Attributes

In addition to Ollama-specific attributes, the scenario also sets generic GenAI attributes:
- `gen_ai.operation.name`: The operation type ("chat" or "generate")
- `gen_ai.request.model`: The model name
- `gen_ai.response.model`: The response model
- `gen_ai.usage.input_tokens`: Input token count
- `gen_ai.usage.output_tokens`: Output token count
- `gen_ai.response.finish_reason`: Reason for completion

## Verification

The scenario is verified by the conformance runner, which checks that:
1. Spans of type `ollama.client.chat` and `ollama.client.generate` are created
2. Required attributes are present
3. Attribute values match expected types and examples

## References

- [Ollama Semantic Conventions](../../../model/ollama/)
- [Ollama Documentation](https://docs.ollama.ai/)
- [Ollama API Reference](https://docs.ollama.ai/api/)
