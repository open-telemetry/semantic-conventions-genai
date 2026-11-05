# mem0

mem0 is a memory library for agents. Its `Memory` class stores and searches
memory records in the vector store it is configured with, so it **owns the
memory operations**. It calls models through provider clients such as
`openai`, so it **delegates inference and embeddings**.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| memory (`create_memory`, `search_memory`) | Yes, `Memory.add(..., infer=False)` and `Memory.search` | ✅ Implemented |
| memory (`upsert_memory`) | Yes, `Memory.add` with the default `infer=True` lets mem0 decide what to store | ❌ Not implemented |
| memory (`update_memory`, `delete_memory`) | Yes, `Memory.update`, `Memory.delete` and `Memory.delete_all` | ❌ Not implemented |
| inference (`chat`), embeddings | No, delegates to the model client (`openai`) | ✅ Correctly not emitted |

`gen_ai.memory.store.id` is not set. mem0 assigns no store identifier; it
scopes records by `user_id`, `agent_id` and `run_id` inside the backend
collection that the application names.
