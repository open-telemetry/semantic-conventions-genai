# deepeval

DeepEval runs metrics over GenAI inputs and outputs, so it owns the evaluation
operation. Metrics that use an LLM judge call a model client, which **delegates
inference** to the underlying LLM library.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| evaluation | Yes — runs metrics and reports results | ✅ Implemented |
| inference (`chat`) | No — LLM-judge metrics delegate to the model client | ✅ Correctly not emitted |
