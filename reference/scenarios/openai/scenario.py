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
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello."},
    ]
    system_instructions = [
        {"parts": [{"type": "text", "content": message["content"]}]}
        for message in messages
        if message["role"] in {"system", "developer"}
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
        span.set_attribute("gen_ai.input.messages", input_messages)
        if system_instructions:
            span.set_attribute("gen_ai.system_instructions", json.dumps(system_instructions))
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


def run_chat_reasoning_reference(client):
    """Scenario: chat completion with a reasoning model (e.g. o-series).

    Exercises `gen_ai.usage.reasoning.output_tokens` capture from
    `completion_tokens_details.reasoning_tokens`, alongside
    `gen_ai.usage.cache_read.input_tokens` from
    `prompt_tokens_details.cached_tokens`.
    """
    print("  [chat_reasoning] reasoning-model chat completion (reference implementation)")
    request_model = "o4-mini"
    messages = [{"role": "user", "content": "Think briefly, then say hello."}]
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
    with _reference_tracer.start_as_current_span("chat o4-mini", attributes=span_attributes) as span:
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
            cached_tokens = getattr(
                getattr(resp.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            if cached_tokens is not None:
                span.set_attribute("gen_ai.usage.cache_read.input_tokens", cached_tokens)
            reasoning_tokens = getattr(
                getattr(resp.usage, "completion_tokens_details", None),
                "reasoning_tokens",
                None,
            )
            if reasoning_tokens is not None:
                span.set_attribute("gen_ai.usage.reasoning.output_tokens", reasoning_tokens)

        event_attrs = {
            "gen_ai.operation.name": "chat",
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
            reasoning_tokens = getattr(
                getattr(resp.usage, "completion_tokens_details", None),
                "reasoning_tokens",
                None,
            )
            if reasoning_tokens is not None:
                event_attrs["gen_ai.usage.reasoning.output_tokens"] = reasoning_tokens
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


def run_chat_audio_reference(client):
    """Scenario: chat completion with audio input and audio output.

    Exercises `gen_ai.usage.{text,audio}.input_tokens` capture from OpenAI's
    `prompt_tokens_details.{text_tokens,audio_tokens}` breakdown and
    `gen_ai.usage.{text,audio}.output_tokens` capture from
    `completion_tokens_details.{text_tokens,audio_tokens}`, reported on the
    `gpt-4o-audio-preview` family.
    """
    import base64

    print("  [chat_audio] audio-input chat completion (reference implementation)")
    request_model = "gpt-4o-audio-preview"
    # Tiny WAV header + silence (44-byte RIFF header, no PCM frames).
    audio_bytes = (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this recording?"},
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
            ],
        }
    ]
    host, port = mock_server_host_port(MOCK_BASE_URL)
    input_messages = json.dumps(
        [
            {
                "role": "user",
                "parts": [
                    {"type": "text", "content": "What is in this recording?"},
                    {"type": "blob", "mime_type": "audio/wav", "modality": "audio"},
                ],
            }
        ]
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
    with _reference_tracer.start_as_current_span("chat gpt-4o-audio-preview", attributes=span_attributes) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.chat.completions.create(
            model=request_model,
            messages=messages,
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "wav"},
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
            prompt_details = getattr(resp.usage, "prompt_tokens_details", None)
            text_input = getattr(prompt_details, "text_tokens", None)
            if text_input is not None:
                span.set_attribute("gen_ai.usage.text.input_tokens", text_input)
            audio_input = getattr(prompt_details, "audio_tokens", None)
            if audio_input is not None:
                span.set_attribute("gen_ai.usage.audio.input_tokens", audio_input)
            completion_details = getattr(resp.usage, "completion_tokens_details", None)
            text_output = getattr(completion_details, "text_tokens", None)
            if text_output is not None:
                span.set_attribute("gen_ai.usage.text.output_tokens", text_output)
            audio_output = getattr(completion_details, "audio_tokens", None)
            if audio_output is not None:
                span.set_attribute("gen_ai.usage.audio.output_tokens", audio_output)

        event_attrs = {
            "gen_ai.operation.name": "chat",
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
            prompt_details = getattr(resp.usage, "prompt_tokens_details", None)
            text_input = getattr(prompt_details, "text_tokens", None)
            if text_input is not None:
                event_attrs["gen_ai.usage.text.input_tokens"] = text_input
            audio_input = getattr(prompt_details, "audio_tokens", None)
            if audio_input is not None:
                event_attrs["gen_ai.usage.audio.input_tokens"] = audio_input
            completion_details = getattr(resp.usage, "completion_tokens_details", None)
            text_output = getattr(completion_details, "text_tokens", None)
            if text_output is not None:
                event_attrs["gen_ai.usage.text.output_tokens"] = text_output
            audio_output = getattr(completion_details, "audio_tokens", None)
            if audio_output is not None:
                event_attrs["gen_ai.usage.audio.output_tokens"] = audio_output
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
            tool_call = choice.message.tool_calls[0]
            arguments_json = tool_call.function.arguments or "{}"
            arguments = json.loads(arguments_json)
            tool_span_attributes = {
                "gen_ai.operation.name": "execute_tool",
            }
            with _reference_tracer.start_as_current_span(
                "execute_tool get_weather", attributes=tool_span_attributes
            ) as tool_span:
                tool_span.set_attribute("gen_ai.tool.name", tool_call.function.name)
                tool_span.set_attribute("gen_ai.tool.description", request_tool["function"]["description"])
                tool_span.set_attribute("gen_ai.tool.type", request_tool["type"])
                tool_span.set_attribute("gen_ai.tool.call.id", tool_call.id)
                tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
                result = get_weather(arguments["location"])
                tool_span.set_attribute("gen_ai.tool.call.result", result)
            print(f"    -> tool_call: {tool_call.function.name}")
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


def run_image_generation_reference(client):
    """Scenario: image generation with the OpenAI Image API.

    Exercises `gen_ai.usage.image.output_tokens` and
    `gen_ai.usage.text.input_tokens` capture from GPT Image's
    `response.usage.{output_tokens,input_tokens_details.text_tokens}`.
    GPT Image models tokenize the generated image and bill per token, so
    `response.usage.output_tokens` is entirely image-modality output.
    """
    print("  [image_generation] image generation (reference implementation)")
    request_model = "gpt-image-1"
    prompt = "A cute otter holding a paintbrush, watercolor style."
    request_size = "1024x1024"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    input_messages = json.dumps(
        [{"role": "user", "parts": [{"type": "text", "content": prompt}]}]
    )
    span_attributes_img = {
        "gen_ai.operation.name": "generate_content",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
    }
    if host:
        span_attributes_img["server.address"] = host
    if port is not None:
        span_attributes_img["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "generate_content gpt-image-1", attributes=span_attributes_img
    ) as span:
        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.images.generate(
            model=request_model,
            prompt=prompt,
            size=request_size,
            n=1,
        )
        output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "blob",
                        "mime_type": "image/png",
                        "modality": "image",
                        "content": resp.data[0].b64_json,
                    }
                ],
            }
        ]
        span.set_attribute("gen_ai.output.messages", json.dumps(output_messages))
        if resp.usage:
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
            input_details = getattr(resp.usage, "input_tokens_details", None)
            text_input = getattr(input_details, "text_tokens", None)
            if text_input is not None:
                span.set_attribute("gen_ai.usage.text.input_tokens", text_input)
            image_input = getattr(input_details, "image_tokens", None)
            if image_input is not None and image_input > 0:
                span.set_attribute("gen_ai.usage.image.input_tokens", image_input)
            # GPT Image: output_tokens are entirely image-modality tokens
            # (the generated image is tokenized for billing).
            span.set_attribute("gen_ai.usage.image.output_tokens", resp.usage.output_tokens)

        event_attrs = {
            "gen_ai.operation.name": "generate_content",
            "gen_ai.request.model": request_model,
            "gen_ai.input.messages": input_messages,
            "gen_ai.output.messages": json.dumps(output_messages),
        }
        if resp.usage:
            event_attrs["gen_ai.usage.input_tokens"] = resp.usage.input_tokens
            event_attrs["gen_ai.usage.output_tokens"] = resp.usage.output_tokens
            input_details = getattr(resp.usage, "input_tokens_details", None)
            text_input = getattr(input_details, "text_tokens", None)
            if text_input is not None:
                event_attrs["gen_ai.usage.text.input_tokens"] = text_input
            image_input = getattr(input_details, "image_tokens", None)
            if image_input is not None and image_input > 0:
                event_attrs["gen_ai.usage.image.input_tokens"] = image_input
            event_attrs["gen_ai.usage.image.output_tokens"] = resp.usage.output_tokens
        if host:
            event_attrs["server.address"] = host
        if port is not None:
            event_attrs["server.port"] = port
        reference_event_logger().emit(
            event_name="gen_ai.client.inference.operation.details",
            body="Inference operation details",
            attributes=event_attrs,
        )

        print(f"    -> image bytes: {len(resp.data[0].b64_json)} (b64)")


def main():
    print("=== Reference Implementation: OpenAI Reference Implementation ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")

    run_chat_reference(client)
    run_chat_streaming_reference(client)
    run_chat_tool_call_reference(client)
    run_chat_with_document_input_reference(client)
    run_embeddings_reference(client)
    run_chat_reasoning_reference(client)
    run_chat_audio_reference(client)
    run_image_generation_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
