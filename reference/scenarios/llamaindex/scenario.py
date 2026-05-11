"""Reference implementation for LlamaIndex."""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_chat_reference(llm, request_model, request_temperature, request_choice_count):
    """Scenario: basic chat completion with reference implementation."""
    from llama_index.core.llms import ChatMessage, MessageRole

    print("  [chat] basic chat completion (reference implementation)")
    host, port = mock_server_host_port(MOCK_BASE_URL)
    user_content = "Say hello."
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.request.choice.count", request_choice_count)
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": "user", "parts": [{"type": "text", "content": user_content}]}]),
        )
        resp = llm.chat([ChatMessage(role=MessageRole.USER, content=user_content)])
        raw = getattr(resp, "raw", None)
        if raw:
            if getattr(raw, "model", None):
                span.set_attribute("gen_ai.response.model", raw.model)
            if getattr(raw, "id", None):
                span.set_attribute("gen_ai.response.id", raw.id)
            if getattr(raw, "choices", None):
                span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in raw.choices])
            if getattr(raw, "usage", None) and raw.usage:
                span.set_attribute("gen_ai.usage.input_tokens", raw.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", raw.usage.completion_tokens)
        span.set_attribute(
            "gen_ai.output.messages",
            json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": str(resp)}],
                        "finish_reason": raw.choices[0].finish_reason
                        if raw and getattr(raw, "choices", None)
                        else None,
                    }
                ]
            ),
        )

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": request_model,
            "gen_ai.request.choice.count": request_choice_count,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": user_content}]}]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": str(resp)}],
                        "finish_reason": raw.choices[0].finish_reason
                        if raw and getattr(raw, "choices", None)
                        else None,
                    }
                ]
            ),
        }
        if raw:
            if getattr(raw, "model", None):
                event_attrs["gen_ai.response.model"] = raw.model
            if getattr(raw, "id", None):
                event_attrs["gen_ai.response.id"] = raw.id
            if getattr(raw, "choices", None):
                event_attrs["gen_ai.response.finish_reasons"] = [c.finish_reason for c in raw.choices]
            if getattr(raw, "usage", None) and raw.usage:
                event_attrs["gen_ai.usage.input_tokens"] = raw.usage.prompt_tokens
                event_attrs["gen_ai.usage.output_tokens"] = raw.usage.completion_tokens
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {str(resp)[:60]}")


def run_chat_streaming_reference(llm, request_model, request_temperature):
    """Scenario: streaming chat completion with reference implementation."""
    from llama_index.core.llms import ChatMessage, MessageRole

    print("  [chat_streaming] streaming chat completion (reference implementation)")
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        text = ""
        finish_reasons = []
        stream_resp = llm.stream_chat([ChatMessage(role=MessageRole.USER, content="Tell me a joke.")])
        for token in stream_resp:
            text += token.delta
            token_raw = getattr(token, "raw", None)
            if token_raw and getattr(token_raw, "choices", None):
                finish_reasons.extend(
                    choice.finish_reason
                    for choice in token_raw.choices
                    if choice.finish_reason and choice.finish_reason not in finish_reasons
                )
        raw = getattr(stream_resp, "raw", None)
        if raw:
            if getattr(raw, "model", None):
                span.set_attribute("gen_ai.response.model", raw.model)
            if getattr(raw, "id", None):
                span.set_attribute("gen_ai.response.id", raw.id)
            if getattr(raw, "choices", None):
                finish_reasons.extend(
                    choice.finish_reason
                    for choice in raw.choices
                    if choice.finish_reason and choice.finish_reason not in finish_reasons
                )
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        print(f"    -> {text[:60]}")


def run_agent_reference(llm, request_model, request_temperature):
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
    function_schema = weather_tool.metadata.fn_schema
    tool_definition = {
        "name": weather_tool.metadata.name,
        "description": weather_tool.metadata.description,
        "fn_schema": (
            function_schema.model_json_schema()
            if function_schema is not None
            else {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            }
        ),
    }
    original_call_tool_with_selection = tool_calling.call_tool_with_selection

    def _capture_call_tool_with_selection(tool_call, tools, verbose=False):
        nonlocal current_tool_call_id
        current_tool_call_id = tool_call.tool_id or None
        return original_call_tool_with_selection(tool_call, tools, verbose=verbose)

    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_3) as span:
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute("gen_ai.tool.definitions", json.dumps([tool_definition]))
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


def run_embeddings_reference():
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    import llama_index.embeddings.openai.base as openai_embedding_base
    from llama_index.embeddings.openai import OpenAIEmbedding

    request_model = "text-embedding-3-small"
    request_encoding_format = "base64"
    captured_response = None
    host, port = mock_server_host_port(MOCK_BASE_URL)
    embed_model = OpenAIEmbedding(
        model_name=request_model,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        additional_kwargs={"encoding_format": request_encoding_format},
    )
    original_get_embedding = openai_embedding_base.get_embedding

    def _capture_get_embedding(client, text, engine, **kwargs):
        nonlocal captured_response
        text = text.replace("\n", " ")
        captured_response = client.embeddings.create(input=[text], model=engine, **kwargs)
        return captured_response.data[0].embedding

    span_attributes_4 = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_4["server.address"] = host
    if port is not None:
        span_attributes_4["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "embeddings text-embedding-3-small", attributes=span_attributes_4
    ) as span:
        span.set_attribute("gen_ai.request.encoding_formats", [request_encoding_format])
        try:
            openai_embedding_base.get_embedding = _capture_get_embedding
            result = embed_model.get_text_embedding("Hello, world!")
        finally:
            openai_embedding_base.get_embedding = original_get_embedding
        span.set_attribute("gen_ai.embeddings.dimension.count", len(result))
        if captured_response is not None:
            if getattr(captured_response, "model", None):
                span.set_attribute("gen_ai.response.model", captured_response.model)
            if getattr(captured_response, "usage", None) and captured_response.usage:
                span.set_attribute("gen_ai.usage.input_tokens", captured_response.usage.prompt_tokens)
        print(f"    -> embedding dim: {len(result)}")


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
    request_top_k = 1.0
    retriever = index.as_retriever(similarity_top_k=int(request_top_k))
    query_text = "Seattle weather"

    with _reference_tracer.start_as_current_span("retrieval weather-knowledge-base") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", data_source_id)
        span.set_attribute("gen_ai.provider.name", "openai")
        span.set_attribute("gen_ai.request.model", request_model)
        span.set_attribute("gen_ai.request.top_k", request_top_k)
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
    request_choice_count = 2
    chat_llm = LlamaOpenAI(
        model=request_model,
        temperature=request_temperature,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
        additional_kwargs={"n": request_choice_count},
    )
    llm = LlamaOpenAI(
        model=request_model,
        temperature=request_temperature,
        api_base=MOCK_BASE_URL,
        api_key="mock-key",
    )

    run_chat_reference(chat_llm, request_model, request_temperature, request_choice_count)
    run_chat_streaming_reference(llm, request_model, request_temperature)
    run_agent_reference(llm, request_model, request_temperature)
    run_embeddings_reference()
    run_retrieval_reference()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
