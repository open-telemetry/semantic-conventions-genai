# instructor

Instructor patches an LLM client (e.g. `openai`) to return structured outputs.
The actual model call is made by the wrapped client, so it **delegates
inference**. It parses the tool call into a Pydantic model and hands it back;
the tool itself runs in application code Instructor never sees.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — wraps and delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| execute_tool | No — Instructor parses the tool call into a model; the tool runs in app code | ❌ Shown, but not instrumentable |
