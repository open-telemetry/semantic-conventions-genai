"""Reference implementation for LlamaIndex."""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_agent_reference(llm):
    """Scenario: agent with tool calling and reference implementation."""
    print("  [chat_tool_call] agent with tool calling (reference implementation)")
    import llama_index.core.tools.calling as tool_calling
    from llama_index.core.tools import FunctionTool

    current_tool_call_id = None

    def get_weather(location: str) -> str:
        """Get the current weather for a location."""
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.description", get_weather.__doc__ or "")
            tool_span.set_attribute("gen_ai.tool.type", "function")
            if current_tool_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", current_tool_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = "Sunny, 72°F"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
            return result

    weather_tool = FunctionTool.from_defaults(fn=get_weather)
    original_call_tool_with_selection = tool_calling.call_tool_with_selection

    def _capture_call_tool_with_selection(tool_call, tools, verbose=False):
        nonlocal current_tool_call_id
        current_tool_call_id = tool_call.tool_id or None
        return original_call_tool_with_selection(tool_call, tools, verbose=verbose)

    try:
        tool_calling.call_tool_with_selection = _capture_call_tool_with_selection
        response = llm.predict_and_call(
            tools=[weather_tool],
            user_msg="What's the weather in Seattle?",
            verbose=False,
        )
    finally:
        tool_calling.call_tool_with_selection = original_call_tool_with_selection
    print(f"    -> {str(response)[:60]}")


def run_retrieval_reference():
    """Scenario: vector retrieval via LlamaIndex retriever with reference implementation."""
    print("  [retrieval] vector retrieval (reference implementation)")
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.embeddings.openai import OpenAIEmbedding

    request_model = "text-embedding-3-small"
    data_source_id = "weather-knowledge-base"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    documents = [
        Document(text="Seattle weather is rainy and cool.", metadata={"source_id": data_source_id}),
    ]
    embed_model = OpenAIEmbedding(
        model_name=request_model,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
    )
    index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)
    top_k = 1
    retriever = index.as_retriever(similarity_top_k=top_k)
    query_text = "Seattle weather"

    with _reference_tracer.start_as_current_span("retrieval weather-knowledge-base") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", data_source_id)
        span.set_attribute("gen_ai.provider.name", "openai")
        span.set_attribute("gen_ai.request.model", request_model)
        span.set_attribute("gen_ai.retrieval.top_k", top_k)
        span.set_attribute("gen_ai.retrieval.query.text", query_text)
        if host:
            span.set_attribute("server.address", host)
        if port is not None:
            span.set_attribute("server.port", port)
        nodes = retriever.retrieve(query_text)
        span.set_attribute(
            "gen_ai.retrieval.documents",
            json.dumps(
                [
                    {
                        "content": node.text,
                        "source_id": node.metadata.get("source_id"),
                    }
                    for node in nodes
                ]
            ),
        )
        print(f"    -> {nodes[0].text[:60]}")


def main():
    print("=== Reference Implementation: LlamaIndex Reference Implementation ===")

    tp, lp, mp = setup_otel()

    from llama_index.llms.openai import OpenAI as LlamaOpenAI

    request_model = "gpt-4o-mini"
    request_temperature = 0.1
    llm = LlamaOpenAI(
        model=request_model,
        temperature=request_temperature,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
    )

    run_agent_reference(llm)
    run_retrieval_reference()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
