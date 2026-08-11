# azure-ai-evaluation

`azure-ai-evaluation` runs evaluators over GenAI inputs and outputs, so it owns
the evaluation operation. Evaluators that use an LLM judge call a model client,
which **delegates inference** to the underlying LLM library.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| evaluation | Yes — runs evaluators and reports results | ✅ Implemented |
| inference (`chat`) | No — LLM-judge evaluators delegate to the model client | ✅ Correctly not emitted |
