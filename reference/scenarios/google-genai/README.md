# google-genai

The `google-genai` client is a **model-call boundary**: it calls the Gemini API
directly, so it owns inference and embeddings. It also supports **automatic
function calling** — when tools are Python callables, the SDK executes them — so
tool execution is instrumentable here.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — calls the model directly | ✅ Implemented |
| execute_tool | Yes — automatic function calling executes the tool | ✅ Implemented |
| create_agent | Yes — `google.genai.Client.agents` supports remote agent creation | ✅ Implemented |
| invoke_agent (client) | Yes — `interactions.create(agent=...)` invokes a remote agent | ❌ Not implemented |

The embeddings error handler records a correlated
`gen_ai.client.embeddings.exception` WARN log. This scenario does not exercise that path.

The model continuation through `interactions.create(model=..., previous_interaction_id=...)`
records a client inference span. Its error handler records a correlated
`gen_ai.client.inference.exception` WARN log. This scenario does not exercise that path.
