"""Reference implementation for Instructor."""

import json
import os

from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_chat_tool_call_reference(client):
    """Scenario: chat with tool calling via Instructor with reference implementation."""
    from pydantic import BaseModel

    print("  [chat_tool_call] chat with tool calling via Instructor (reference implementation)")
    request_model = "gpt-4o-mini"

    class WeatherRequest(BaseModel):
        """Structured weather request arguments."""

        location: str

    tools = [
        {
            "type": "function",
            "function": {
                "name": WeatherRequest.__name__,
                "description": (WeatherRequest.__doc__ or "").strip(),
                "parameters": WeatherRequest.model_json_schema(),
            },
        }
    ]

    def get_weather(location: str) -> str:
        return f"Sunny in {location}"

    messages = [{"role": "user", "content": "What's the weather in Seattle?"}]
    resp, completion = client.chat.completions.create_with_completion(
        model=request_model,
        messages=messages,
        response_model=WeatherRequest,
    )
    tool_calls = getattr(completion.choices[0].message, "tool_calls", None)
    if tool_calls:
        tool_call = tool_calls[0]
        arguments_json = tool_call.function.arguments or json.dumps({"location": resp.location})
        arguments = json.loads(arguments_json)
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool WeatherRequest", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.name", tool_call.function.name)
            tool_span.set_attribute("gen_ai.tool.description", tools[0]["function"]["description"])
            tool_span.set_attribute("gen_ai.tool.type", tools[0]["type"])
            if getattr(tool_call, "id", None):
                tool_span.set_attribute("gen_ai.tool.call.id", tool_call.id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
            result = get_weather(arguments.get("location", resp.location))
            tool_span.set_attribute("gen_ai.tool.call.result", result)
        print(f"    -> tool_call: {tool_call.function.name}")
    else:
        print(f"    -> {resp.location}")


def main():
    print("=== Reference Implementation: Instructor ===")

    tp, lp, mp = setup_otel()

    import openai
    from instructor.core.client import from_openai

    client = from_openai(
        openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key"),
    )

    run_chat_tool_call_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
