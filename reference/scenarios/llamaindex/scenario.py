"""Reference implementation for LlamaIndex."""

import json
import os
import time

from opentelemetry.trace import StatusCode
from reference_shared import (
    flush_and_shutdown,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
EMBEDDING_MODEL = "text-embedding-3-small"

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()
_retrieval_duration = _reference_meter.create_histogram(
    name="gen_ai.retrieval.duration",
    unit="s",
    description="The duration of a single retrieval operation.",
    explicit_bucket_boundaries_advisory=[
        0.01,
        0.02,
        0.04,
        0.08,
        0.16,
        0.32,
        0.64,
        1.28,
        2.56,
        5.12,
        10.24,
        20.48,
        40.96,
        81.92,
    ],
)


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


def retrieve_reference(retriever, query_text):
    """Wrap a LlamaIndex retriever call in a retrieval span and duration metric."""
    # The query embeddings call inside retrieve() belongs to the embeddings
    # instrumentation, so the retrieval span carries no provider, model, or server.
    metric_attributes = {"gen_ai.operation.name": "retrieval"}
    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        "retrieval", attributes=metric_attributes, record_exception=False
    ) as span:
        try:
            span.set_attribute("gen_ai.retrieval.top_k", retriever.similarity_top_k)
            span.set_attribute("gen_ai.retrieval.query.text", query_text)
            nodes = retriever.retrieve(query_text)
            span.set_attribute(
                "gen_ai.retrieval.documents",
                json.dumps([{"id": node.node_id, "score": node.score} for node in nodes]),
            )
            return nodes
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes = {**metric_attributes, "error.type": type(e).__qualname__}
            raise
        finally:
            _retrieval_duration.record(time.perf_counter() - start_time, metric_attributes)


def build_index():
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.embeddings.openai import OpenAIEmbedding

    documents = [
        Document(text="Seattle weather is rainy and cool."),
        Document(text="Paris weather is mild and breezy."),
        Document(text="London weather is cloudy and damp."),
    ]
    embed_model = OpenAIEmbedding(
        model_name=EMBEDDING_MODEL,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
    )
    return VectorStoreIndex.from_documents(documents, embed_model=embed_model)


def run_retrieval_reference(index):
    """Scenario: vector retrieval via LlamaIndex retriever with reference implementation."""
    print("  [retrieval] vector retrieval (reference implementation)")
    nodes = retrieve_reference(index.as_retriever(similarity_top_k=2), "Seattle weather")
    print(f"    -> {nodes[0].text[:60]}")


def run_retrieval_error_reference(index):
    """Scenario: retrieval fails when the query embeddings call is rejected."""
    print("  [retrieval] query embeddings error (reference implementation)")
    import httpx
    import openai
    from llama_index.embeddings.openai import OpenAIEmbedding

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={"error": {"message": "Invalid input", "type": "invalid_request_error", "code": "invalid_input"}},
        )
    )
    failing_embed_model = OpenAIEmbedding(
        model_name=EMBEDDING_MODEL,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        max_retries=0,
        http_client=httpx.Client(transport=transport),
    )
    retriever = index.as_retriever(similarity_top_k=1, embed_model=failing_embed_model)
    try:
        retrieve_reference(retriever, "Seattle weather")
    except openai.BadRequestError:
        print("    -> retrieval failed as expected")
    else:
        raise AssertionError("Expected the query embeddings request to be rejected")


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
    index = build_index()
    run_retrieval_reference(index)
    run_retrieval_error_reference(index)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
