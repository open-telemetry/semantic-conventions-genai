"""Reference implementation: OpenAI Assistants invoke_agent with manual instrumentation.

Exercises: invoke_agent (OpenAI Assistants API: create thread, run, poll)
against a mock OpenAI server, with manual span instrumentation.
"""

import json
import os
from urllib.parse import urlparse

from openai import OpenAI
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
_parsed = urlparse(MOCK_BASE_URL)
_SERVER_ADDRESS = _parsed.hostname or "localhost"
_SERVER_PORT = _parsed.port or 443

tracer = trace.get_tracer("gen_ai.client.openai")


def run_invoke_agent(client):
    """Exercise OpenAI Assistants API with manual OTel spans.

    Creates a CLIENT span with gen_ai invoke_agent attributes to demonstrate
    what an instrumentation library should capture for the Assistants API
    (create assistant, create thread, add message, create run, poll, get messages).
    """
    print("  [invoke_agent] OpenAI Assistants: create + run")
    request_model = "gpt-4o-mini"
    assistant_name = "refimpl-test-assistant"
    assistant_instructions = "You are a helpful assistant."
    assistant_description = "Reference assistant for the OpenAI Assistants API flow."
    request_temperature = 0.2
    request_top_p = 0.9
    request_max_tokens = 128

    def get_weather(location):
        return f"Sunny in {location}"

    tool_defs = [
        {
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
    ]

    # Create assistant
    span_attributes = {
        "gen_ai.operation.name": "create_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": assistant_name,
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span("create_agent", kind=SpanKind.CLIENT, attributes=span_attributes) as span:
        span.set_attribute("gen_ai.agent.description", assistant_description)
        span.set_attribute(
            "gen_ai.system_instructions", json.dumps([{"parts": [{"type": "text", "content": assistant_instructions}]}])
        )
        assistant = client.beta.assistants.create(
            model=request_model,
            name=assistant_name,
            description=assistant_description,
            instructions=assistant_instructions,
            tools=tool_defs,
        )
        span.set_attribute("gen_ai.agent.id", assistant.id)

    # Create thread
    thread = client.beta.threads.create()

    # Add message
    user_message = "Hello, assistant!"
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Create run and wrap in manual invoke_agent span
    span_attributes_2 = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.name": assistant.name or "",
        "server.address": _SERVER_ADDRESS,
        "server.port": _SERVER_PORT,
    }
    with tracer.start_as_current_span("invoke_agent", kind=SpanKind.CLIENT, attributes=span_attributes_2) as span:
        span.set_attribute("gen_ai.agent.id", assistant.id)
        span.set_attribute("gen_ai.request.temperature", request_temperature)
        span.set_attribute("gen_ai.request.top_p", request_top_p)
        span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
        span.set_attribute("gen_ai.conversation.id", thread.id)
        if assistant.description:
            span.set_attribute("gen_ai.agent.description", assistant.description)
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": "user", "parts": [{"type": "text", "content": user_message}]}]),
        )
        span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
        if getattr(assistant, "instructions", None):
            span.set_attribute(
                "gen_ai.system_instructions",
                json.dumps([{"parts": [{"type": "text", "content": assistant.instructions}]}]),
            )
        try:
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id,
                model=request_model,
                max_completion_tokens=request_max_tokens,
                temperature=request_temperature,
                top_p=request_top_p,
            )

            if run.status == "requires_action":
                tool_outputs = []
                required_action = getattr(run, "required_action", None)
                submit_tool_outputs = getattr(required_action, "submit_tool_outputs", None)
                tool_calls = getattr(submit_tool_outputs, "tool_calls", []) or []

                for tool_call in tool_calls:
                    function_call = getattr(tool_call, "function", None)
                    tool_call_id = getattr(tool_call, "id", None)
                    tool_name = getattr(function_call, "name", "get_weather")
                    tool_definition = next(
                        (
                            definition
                            for definition in tool_defs
                            if definition.get("function", {}).get("name") == tool_name
                        ),
                        None,
                    )
                    arguments_json = getattr(function_call, "arguments", "{}") or "{}"
                    arguments = json.loads(arguments_json)

                    tool_span_attributes = {
                        "gen_ai.operation.name": "execute_tool",
                    }
                    with tracer.start_as_current_span(
                        "execute_tool", kind=SpanKind.CLIENT, attributes=tool_span_attributes
                    ) as tool_span:
                        tool_span.set_attribute("gen_ai.tool.name", tool_name)
                        tool_span.set_attribute(
                            "gen_ai.tool.description",
                            (tool_definition or {}).get("function", {}).get("description", ""),
                        )
                        tool_span.set_attribute("gen_ai.tool.type", "function")
                        if tool_call_id:
                            tool_span.set_attribute("gen_ai.tool.call.id", tool_call_id)
                        tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
                        result = get_weather(arguments["location"])
                        tool_span.set_attribute("gen_ai.tool.call.result", result)

                    tool_outputs.append(
                        {
                            "tool_call_id": tool_call_id,
                            "output": result,
                        }
                    )

                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )

            # Poll for completion (mock returns completed immediately)
            if run.status != "completed":
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id,
                )

            if run.usage:
                span.set_attribute("gen_ai.usage.input_tokens", run.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", run.usage.completion_tokens)

            # Get messages
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            assistant_messages = [m for m in messages.data if m.role == "assistant"]
            if assistant_messages:
                text = assistant_messages[0].content[0].text.value
                span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": text}],
                            }
                        ]
                    ),
                )
                print(f"    -> {text[:60]}")
            else:
                print("    -> (no assistant response)")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise

    # Clean up
    client.beta.assistants.delete(assistant.id)


if __name__ == "__main__":
    print("=== Manual: OpenAI Assistants Invoke Agent Reference Implementation ===")
    tp, lp, mp = setup_otel()

    client = OpenAI(
        api_key="mock-key",
        base_url=f"{MOCK_BASE_URL}/v1",
    )

    run_invoke_agent(client)

    flush_and_shutdown(tp, lp, mp)
