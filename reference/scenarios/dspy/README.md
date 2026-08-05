# dspy

DSPy programs run and evaluate LLM modules. It owns the evaluation operation
(`dspy.Evaluate`). Model calls go through `dspy.LM`, which **delegates
inference** to the underlying LLM client.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| evaluation | Yes — runs the metric over program predictions | ✅ Implemented |
| inference (`chat`) | No — `dspy.LM` delegates to the model client | ✅ Correctly not emitted |
