# instructor

Instructor patches an LLM client (e.g. `openai`) to return structured outputs.
The actual model call is made by the wrapped client, so it **delegates
inference**. It owns the tool execution it drives from the structured tool call.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — wraps and delegates to the LLM client (`openai`) | ✅ Correctly not emitted |
| execute_tool | Yes — app-side execution from the structured tool call | ✅ Implemented |
