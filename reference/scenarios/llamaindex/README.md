# llamaindex

LlamaIndex is a data framework for RAG and agents. It calls models through LLM
integrations, so it **delegates inference**. It owns the retrieval, tool, and
workflow operations it runs directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model provider (e.g. `openai`) | ✅ Correctly not emitted |
| retrieval | Yes — retriever / query engine | ✅ Implemented |
| execute_tool | Yes — LlamaIndex runs the tool | ✅ Implemented |
| invoke_workflow | Yes — `Workflow` / query pipeline execution | ❌ Not implemented |
