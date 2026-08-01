"""Reference implementation for OpenAI."""

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


def response_has_compaction_item(response):
    """Return whether the Responses API output includes a ResponseCompactionItem."""
    for item in getattr(response, "output", []) or []:
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if item_type == "compaction":
            return True
    return False


def responses_output_messages(response):
    """Convert Responses API output items into OTel output messages."""
    output_messages = []
    pending_parts = []
    for item in getattr(response, "output", []) or []:
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if item_type == "compaction":
            compaction_part = {"type": "compaction"}
            compaction_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            if compaction_id:
                compaction_part["id"] = compaction_id
            if output_messages and output_messages[-1].get("role") == "assistant":
                output_messages[-1]["parts"].append(compaction_part)
            else:
                pending_parts.append(compaction_part)
            continue
        if item_type != "message":
            continue
        role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        parts = pending_parts
        pending_parts = []
        for block in content or []:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type != "output_text":
                continue
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text:
                parts.append({"type": "text", "content": text})
        if parts:
            output_messages.append({"role": role or "assistant", "parts": parts, "finish_reason": "stop"})
    if pending_parts:
        output_messages.append({"role": "assistant", "parts": pending_parts, "finish_reason": "compaction"})
    return output_messages


def run_chat_reference(client):
    """Scenario: basic chat completion with reference implementation."""
    print("  [chat] basic chat completion (reference implementation)")
    request_model = "gpt-4o-mini"
    request_choice_count = 2
    request_max_tokens = 32
    request_temperature = 0.2
    request_seed = 7
    request_stop_sequences = ["###", "<END>"]
    request_frequency_penalty = 0.1
    request_presence_penalty = 0.2
    request_top_p = 0.9
    request_reasoning_level = "medium"
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    input_messages = json.dumps(
        [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
    )
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
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute("gen_ai.request.seed", request_seed)
        span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
        span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
        span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
        span.set_attribute("gen_ai.request.top_p", request_top_p)
        span.set_attribute("gen_ai.request.reasoning.level", request_reasoning_level)
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
            n=request_choice_count,
            max_tokens=request_max_tokens,
            temperature=request_temperature,
            seed=request_seed,
            stop=request_stop_sequences,
            frequency_penalty=request_frequency_penalty,
            presence_penalty=request_presence_penalty,
            top_p=request_top_p,
            reasoning_effort=request_reasoning_level,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        output_messages = [
            {
                "role": c.message.role,
                "parts": [{"type": "text", "content": c.message.content}],
                "finish_reason": c.finish_reason,
            }
            for c in resp.choices
        ]
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            cached_tokens = getattr(
                getattr(resp.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            if cached_tokens is not None:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", cached_tokens)

        # Emit inference operation details event
        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": [c.finish_reason for c in resp.choices],
            "gen_ai.input.messages": input_messages,
            "gen_ai.output.messages": json.dumps(output_messages),
        }
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.prompt_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.completion_tokens
            cached_tokens = getattr(
                getattr(resp.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            if cached_tokens is not None:
                event_attrs["gen_ai.usage.cache_read.input_tokens"] = cached_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_responses_compaction_reference(client):
    """Scenario: Responses API server-side compaction signal from output items."""
    print("  [responses_compaction] responses with server-side compaction (reference implementation)")
    request_model = "gpt-4o-mini"
    conversation = [
        {
            "type": "message",
            "role": "user",
            "content": "Let's continue a long implementation task.",
        }
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "openai.api.type": "responses",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": "user", "parts": [{"type": "text", "content": conversation[0]["content"]}]}]),
        )
        response = client.responses.create(
            model=request_model,
            input=conversation,
            store=False,
            context_management=[{"type": "compaction", "compact_threshold": 200000}],
        )

        # Provider-side instrumentation derives this from the live SDK
        # response: a ResponseCompactionItem (`type: "compaction"`) in
        # response.output. The request option alone is not enough.
        conversation_compacted = response_has_compaction_item(response)
        span.set_attribute("gen_ai.conversation.compacted", conversation_compacted)
        span.set_attribute("gen_ai.response.model", response.model)
        span.set_attribute("gen_ai.response.id", response.id)
        output_messages = responses_output_messages(response)
        if output_messages:
            span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if response.usage:
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.conversation.compacted": conversation_compacted,
            "gen_ai.request.model": request_model,
            "gen_ai.response.id": response.id,
            "gen_ai.response.model": response.model,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": conversation[0]["content"]}]}]
            ),
        }
        if output_messages:
            event_attrs["gen_ai.output.messages"] = json.dumps(output_messages)
        if response.usage:
            event_attrs["gen_ai.usage.input_tokens"] = response.usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = response.usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )
        print(f"    -> compacted: {conversation_compacted}")


def run_responses_continuation_reference(client):
    """Scenario: Responses API continuation with previous_response_id."""
    print("  [responses_continuation] responses with previous_response_id (reference implementation)")
    request_model = "gpt-4o-mini"
    initial_conversation = [
        {
            "type": "message",
            "role": "user",
            "content": "Initial prompt.",
        }
    ]
    initial_response = client.responses.create(
        model=request_model,
        input=initial_conversation,
    )
    previous_response_id = initial_response.id

    continuation_conversation = [
        {
            "type": "message",
            "role": "user",
            "content": "Follow up on previous response.",
        }
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.request.previous_response.id": previous_response_id,
        "openai.api.type": "responses",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port

    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": continuation_conversation[0]["content"]}]}]
            ),
        )
        response = client.responses.create(
            model=request_model,
            previous_response_id=previous_response_id,
            input=continuation_conversation,
        )

        span.set_attribute("gen_ai.response.model", response.model)
        span.set_attribute("gen_ai.response.id", response.id)
        output_messages = responses_output_messages(response)
        if output_messages:
            span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if response.usage:
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": request_model,
            "gen_ai.request.previous_response.id": previous_response_id,
            "gen_ai.response.id": response.id,
            "gen_ai.response.model": response.model,
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": continuation_conversation[0]["content"]}]}]
            ),
        }
        if output_messages:
            event_attrs["gen_ai.output.messages"] = json.dumps(output_messages)
        if response.usage:
            event_attrs["gen_ai.usage.input_tokens"] = response.usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = response.usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )
        print(f"    -> previous_response_id: {previous_response_id}")


def run_chat_streaming_reference(client):
    """Scenario: streaming chat completion with reference implementation."""
    print("  [chat_streaming] streaming chat completion (reference implementation)")
    request_model = "gpt-4o-mini"
    request_messages = [{"role": "user", "content": "Tell me a joke."}]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_2 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.request.stream": True,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_2) as span:
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in request_messages]
            ),
        )
        stream = client.chat.completions.create(
            model=request_model,
            messages=request_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        text = ""
        model = None
        response_id = None
        finish_reasons = []
        input_tokens = None
        output_tokens = None
        for chunk in stream:
            model = model or getattr(chunk, "model", None)
            response_id = response_id or getattr(chunk, "id", None)
            if chunk.choices and chunk.choices[0].delta.content:
                text += chunk.choices[0].delta.content
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reasons.append(chunk.choices[0].finish_reason)
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
        if model:
            span.set_attribute("gen_ai.response.model", model)
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        if text:
            output_message = {
                "role": "assistant",
                "parts": [{"type": "text", "content": text}],
            }
            if finish_reasons:
                output_message["finish_reason"] = finish_reasons[-1]
            span.set_attribute("gen_ai.output.messages", json.dumps([output_message]))
        if input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        print(f"    -> {text[:60]}")


def run_chat_tool_call_reference(client):
    """Scenario: chat with tool calling with reference implementation."""
    print("  [chat_tool_call] chat with tool calling (reference implementation)")
    request_model = "gpt-4o-mini"

    def get_weather(location: str) -> str:
        return f"Sunny in {location}"

    request_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    }
    tools = [request_tool]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_3 = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_3["server.address"] = host
    if port is not None:
        span_attributes_3["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_3) as span:
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tools))
        resp = client.chat.completions.create(
            model=request_model,
            messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
            tools=tools,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        choice = resp.choices[0]
        if choice.message.tool_calls:
            # The base client returns the tool call; running it is app code the
            # client never sees, so there is no execute_tool span to emit here.
            print(f"    -> tool_call: {choice.message.tool_calls[0].function.name}")
        else:
            print(f"    -> {choice.message.content[:60]}")


def run_chat_with_document_input_reference(client):
    """Scenario: chat with an inline PDF document attachment (document modality).

    Exercises the `document` value of the `Modality` enum on a `BlobPart`
    in `gen_ai.input.messages`. Every emitted field on the BlobPart is
    derivable directly from the OpenAI SDK call boundary:

    - The SDK call passes a `{"type": "file", "file": {"file_data": "data:application/pdf;base64,..."}}`
      content block. The `file_data` value is a data-URI a native
      instrumentation can parse without a separate Files-API roundtrip.
    - `mime_type` comes from the data-URI prefix (`application/pdf`).
    - `content` is the base64 payload of the data-URI.
    - `modality: "document"` is the classification of `application/pdf`
      under the new enum value -- the whole point of this PR.
    """
    import base64

    print("  [chat_document] chat with inline PDF document input (reference implementation)")
    request_model = "gpt-4o-mini"
    instruction = "Summarize the attached document in one sentence."
    # Minimal valid-looking PDF bytes; the mock LLM does not parse this.
    pdf_bytes = b"%PDF-1.4\n%mock pdf for reference scenario\n%%EOF\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    mime_type = "application/pdf"
    data_uri = f"data:{mime_type};base64,{pdf_b64}"
    filename = "sample-kyc.pdf"

    # SDK boundary: documented `file` content block with inline `file_data`.
    user_content = [
        {"type": "text", "text": instruction},
        {"type": "file", "file": {"file_data": data_uri, "filename": filename}},
    ]
    messages = [{"role": "user", "content": user_content}]

    # Canonical OTel parts: TextPart + BlobPart(modality="document"). Each
    # field on the BlobPart traces back to the SDK arg above:
    #   - mime_type: parsed from the data-URI prefix
    #   - content:   the base64 portion of the data-URI
    #   - modality:  derived classification of mime_type "application/pdf"
    input_parts = [
        {"type": "text", "content": instruction},
        {
            "type": "blob",
            "modality": "document",
            "mime_type": mime_type,
            "content": pdf_b64,
        },
    ]
    input_messages = json.dumps([{"role": "user", "parts": input_parts}])

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes_doc = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_doc["server.address"] = host
    if port is not None:
        span_attributes_doc["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes_doc) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in resp.choices])
        output_messages = [
            {
                "role": c.message.role,
                "parts": [{"type": "text", "content": c.message.content}],
                "finish_reason": c.finish_reason,
            }
            for c in resp.choices
        ]
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        print(f"    -> {resp.choices[0].message.content[:60]}")


def run_embeddings_reference(client):
    """Scenario: embedding generation with reference implementation."""
    print("  [embeddings] embedding generation (reference implementation)")
    request_model = "text-embedding-3-small"
    request_encoding_format = "base64"
    host, port = mock_server_host_port(MOCK_BASE_URL)
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
        resp = client.embeddings.create(
            model=request_model,
            input="Hello, world!",
            encoding_format=request_encoding_format,
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        if resp.data and resp.data[0].embedding is not None:
            span.set_attribute("gen_ai.embeddings.dimension.count", len(resp.data[0].embedding))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
        print(f"    -> embedding dim: {len(resp.data[0].embedding)}")


def run_responses_with_prompt_template_reference(client):
    """Scenario: OpenAI Responses API with a stored prompt template.

    The Responses API accepts a `prompt` parameter that references a stored
    prompt template by id, with optional version and variables. The
    instrumentation extracts gen_ai.prompt.name, gen_ai.prompt.version,
    and gen_ai.prompt.variable.* from the request.
    """
    print("  [responses_prompt_template] Responses API with prompt template (reference implementation)")
    request_model = "gpt-4o-mini"
    prompt_id = "customer-support"
    prompt_version = "1.2.0"
    prompt_variables = {"user_name": "Alice", "language": "French"}
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.prompt.name": prompt_id,
        "gen_ai.prompt.version": prompt_version,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("chat gpt-4o-mini", attributes=span_attributes) as span:
        for var_name, var_value in prompt_variables.items():
            span.set_attribute(f"gen_ai.prompt.variable.{var_name}", var_value)
        resp = client.responses.create(
            model=request_model,
            input="Help me with my order.",
            prompt={
                "id": prompt_id,
                "version": prompt_version,
                "variables": prompt_variables,
            },
        )
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.response.id", resp.id)
        output_text = None
        for output in getattr(resp, "output", []) or []:
            if getattr(output, "type", None) == "message":
                for content in getattr(output, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        output_text = getattr(content, "text", None)
                        break
        if output_text:
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": output_text}],
                            "finish_reason": "stop",
                        }
                    ]
                ),
            )
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
        span.set_attribute("gen_ai.response.finish_reasons", ["stop"])

        event_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": request_model,
            "gen_ai.prompt.name": prompt_id,
            "gen_ai.prompt.version": prompt_version,
            "gen_ai.response.id": resp.id,
            "gen_ai.response.model": resp.model,
            "gen_ai.response.finish_reasons": ["stop"],
        }
        for var_name, var_value in prompt_variables.items():
            event_attrs[f"gen_ai.prompt.variable.{var_name}"] = var_value
        if output_text:
            event_attrs["gen_ai.output.messages"] = json.dumps(
                [{"role": "assistant", "parts": [{"type": "text", "content": output_text}], "finish_reason": "stop"}]
            )
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> {(output_text or '')[:60]}")


def _fetch_response_finish_reason(fetched):
    """Map a fetched Responses `status` to a `gen_ai.response.finish_reasons` value.

    The fetch itself always succeeds here; this conveys the outcome of the
    ORIGINAL generation recorded on the response. A completed generation maps to
    its stop reason, an incomplete one to why it was cut short, and a failed or
    cancelled generation to `error`.

    Returns None for non-terminal statuses (`queued`, `in_progress`): generation
    has not stopped yet, so there is no finish reason to record. The lifecycle
    state is conveyed by `gen_ai.response.status` instead.
    """
    status = getattr(fetched, "status", None)
    if status in ("queued", "in_progress"):
        return None
    if status == "completed":
        return "stop"
    if status == "incomplete":
        details = getattr(fetched, "incomplete_details", None)
        reason = getattr(details, "reason", None) if details else None
        if reason == "max_output_tokens":
            return "length"
        if reason == "content_filter":
            return "content_filter"
        return "incomplete"
    return "error"


def _emit_fetch_response_span(client, response_id, starting_after=None):
    """Fetch a response by id and emit the `gen_ai.fetch_response.client` span.

    Owns its own span boundary, so all attributes are set inline here. Every
    value is derived from the retrieve-call boundary:

    - `gen_ai.response.id`, `gen_ai.response.model` come from the fetched object.
    - `gen_ai.response.status` conveys the lifecycle state of the fetched response
      (for example `completed` or `failed`), taken from the fetched `status` field.
    - `gen_ai.response.finish_reasons` conveys the ORIGINAL generation's outcome,
      derived from the fetched `status`/`incomplete_details` (see helper above).
      It is only recorded for terminal statuses; a still-`queued` or `in_progress`
      response has no finish reason. A fetched response whose original generation
      failed or is incomplete is NOT an error of this fetch, so `error.type`/span
      status are not set for it.
    - `gen_ai.system_instructions` and `gen_ai.output.messages` are the content
      carried by the fetched response. The original input messages are NOT part
      of the fetched response object, so `gen_ai.input.messages` is not recorded.
    - `gen_ai.request.stream_cursor` is the resume cursor (OpenAI `starting_after`),
      a request-side parameter available at the call boundary, recorded only when
      the fetch resumes a streamed response from a prior position.
    - Token usage is intentionally NOT recorded: no inference happens here, and
      the fetched response's token counts belong to the original generation.
      Recording them would double-count tokens when summing spans in a
      multi-step run.
    - `openai.api.type` is `responses`; `openai.response.service_tier` comes from
      the fetched object.
    """
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "fetch_response",
        "gen_ai.provider.name": "openai",
        "gen_ai.response.id": response_id,
        "openai.api.type": "responses",
    }
    if starting_after is not None:
        span_attributes["gen_ai.request.stream_cursor"] = str(starting_after)
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span("fetch_response", attributes=span_attributes) as span:
        if starting_after is not None:
            # Resume the streamed response from the cursor. The terminal
            # `response.completed` event carries the full response object.
            fetched = None
            for event in client.responses.retrieve(response_id, stream=True, starting_after=starting_after):
                candidate = getattr(event, "response", None)
                if candidate is not None:
                    fetched = candidate
        else:
            fetched = client.responses.retrieve(response_id)
        span.set_attribute("gen_ai.response.id", fetched.id)
        span.set_attribute("gen_ai.response.model", fetched.model)
        status = getattr(fetched, "status", None)
        if status is not None:
            span.set_attribute("gen_ai.response.status", status)
        finish_reason = _fetch_response_finish_reason(fetched)
        if finish_reason is not None:
            span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])
        service_tier = getattr(fetched, "service_tier", None)
        if service_tier is not None:
            span.set_attribute("openai.response.service_tier", service_tier)
        # Content carried on the fetched response: system instructions and output
        # messages. The original input messages are NOT part of the fetched
        # response, so `gen_ai.input.messages` is not set here.
        instructions = getattr(fetched, "instructions", None)
        if instructions:
            span.set_attribute(
                "gen_ai.system_instructions",
                json.dumps([{"type": "text", "content": instructions}]),
            )
        output_messages = responses_output_messages(fetched)
        if output_messages:
            span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        # Token usage is intentionally NOT recorded on this span: no inference
        # happens on a fetch, and the fetched response's token counts belong to
        # the original generation (already accounted for on that operation).
        print(f"    -> fetched {fetched.id} (status={getattr(fetched, 'status', None)})")


def run_fetch_response_reference(client):
    """Scenario: fetch a previously generated Responses API result by its id.

    Emits the `gen_ai.fetch_response.client` span (OpenAI `openai.fetch_response.client`
    refinement) around `client.responses.retrieve(...)`. This operation performs
    no inference: a response is first created with `store=True`, then fetched by
    id. A background streaming response is then created, consumed until the
    caller disconnects, and resumed from the last event's cursor to show
    `gen_ai.request.stream_cursor` being recorded. A final fetch retrieves a
    response whose original generation failed, to show that the fetch still
    succeeds and the failure is conveyed through `gen_ai.response.finish_reasons`
    rather than as an error of the fetch.
    """
    print("  [fetch_response] fetch a stored Responses API result by id (reference implementation)")
    request_model = "gpt-4o-mini"

    # Create a stored response first so there is a real id to fetch. This
    # create call is a separate inference operation and not part of the
    # fetch_response span below.
    created = client.responses.create(
        model=request_model,
        instructions="You are a helpful assistant.",
        input="Say hello.",
        store=True,
    )
    _emit_fetch_response_span(client, created.id)

    # Resume a streamed fetch from a real cursor. Only a background response
    # created with streaming can be resumed by id, so create one, consume it
    # until the caller "disconnects" (the stream ends before completion), and
    # capture the last event's sequence_number. Resuming with that cursor lets a
    # generic instrumentation record it as `gen_ai.request.stream_cursor`.
    background = client.responses.create(
        model=request_model,
        instructions="You are a helpful assistant.",
        input="Say hello.",
        background=True,
        stream=True,
        store=True,
    )
    background_id = None
    last_sequence_number = None
    for event in background:
        response_obj = getattr(event, "response", None)
        if response_obj is not None:
            background_id = response_obj.id
        sequence_number = getattr(event, "sequence_number", None)
        if sequence_number is not None:
            last_sequence_number = sequence_number
    _emit_fetch_response_span(client, background_id, starting_after=last_sequence_number)

    # Fetch a response whose original generation failed. The fetch succeeds; the
    # failure surfaces only via gen_ai.response.finish_reasons.
    _emit_fetch_response_span(client, "resp-failed-001")


def main():
    print("=== Reference Implementation: OpenAI Reference Implementation ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")

    run_chat_reference(client)
    run_responses_compaction_reference(client)
    run_responses_continuation_reference(client)
    run_chat_streaming_reference(client)
    run_chat_tool_call_reference(client)
    run_chat_with_document_input_reference(client)
    run_responses_with_prompt_template_reference(client)
    run_fetch_response_reference(client)
    run_embeddings_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
