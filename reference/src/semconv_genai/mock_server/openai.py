"""OpenAI-compatible chat / embeddings / responses endpoints."""

import copy
import json

from flask import Blueprint, Response, request

from ._common import mock_tool_arguments, sse

bp = Blueprint("openai", __name__)


CHAT_REFUSAL_RESPONSE = {
    "id": "chatcmpl-mock-refusal-001",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "refusal": "I am unable to produce structured output for that request.",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 30,
        "completion_tokens": 18,
        "total_tokens": 48,
    },
}


CHAT_RESPONSE = {
    "id": "chatcmpl-mock-001",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "This is a response from the mock server.",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 12,
        "total_tokens": 37,
    },
}

CHAT_TOOL_CALL_RESPONSE = {
    "id": "chatcmpl-mock-002",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mock_001",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "Seattle"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 70,
    },
}

EMBEDDING_RESPONSE = {
    "id": "embd-mock-001",
    "object": "list",
    "data": [
        {
            "object": "embedding",
            "index": 0,
            "embedding": [0.001] * 256,
        }
    ],
    "model": "text-embedding-3-small",
    "usage": {
        "prompt_tokens": 8,
        "total_tokens": 8,
    },
}

RESPONSES_RESPONSE = {
    "id": "resp-mock-001",
    "object": "response",
    "created_at": 1700000000,
    "model": "gpt-4o-mini",
    "output": [
        {
            "type": "message",
            "id": "msg-mock-001",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "This is a response from the mock server.",
                }
            ],
        }
    ],
    "usage": {
        "input_tokens": 25,
        "output_tokens": 12,
        "total_tokens": 37,
    },
}


def _mock_chat_content(body, message_text):
    # CrewAI converter retry: when convert_with_instructions builds a
    # Converter and calls to_pydantic(), the LLM call carries CrewAI's
    # schema-conversion system prompt ("Format your final answer ...", from
    # crewai/translations/en.json formatted_task_instructions). Detect the
    # literal text and return a valid PlannerTaskPydanticOutput-shaped JSON
    # body so the conversion succeeds.
    if "Format your final answer according to the following OpenAPI schema" in message_text:
        return json.dumps(
            {
                "list_of_plans_per_task": [
                    {
                        "task_number": 1,
                        "task": "task 1",
                        "plan": (
                            "Step 1: Identify the inputs required for task 1. "
                            "Step 2: Run the appropriate tool. "
                            "Step 3: Summarize the result."
                        ),
                    }
                ]
            }
        )

    # CrewAI CrewPlanner: detect via the planning agent's role string and
    # return a PlannerTaskPydanticOutput-shaped JSON body that
    # crewai.utilities.converter.validate_model can model_validate_json into
    # PlannerTaskPydanticOutput. The number of plans returned matches the
    # number of "Task Number N -" markers the planner injects into the user
    # message via CrewPlanner._create_tasks_summary.
    if "Task Execution Planner" in message_text:
        task_count = max(1, message_text.count("Task Number "))
        plans = [
            {
                "task_number": i + 1,
                "task": f"task {i + 1}",
                "plan": (
                    f"Step 1: Identify the inputs required for task {i + 1}. "
                    "Step 2: Run the appropriate tool. "
                    "Step 3: Summarize the result."
                ),
            }
            for i in range(task_count)
        ]
        return json.dumps({"list_of_plans_per_task": plans})

    # langchain-experimental Plan-and-Execute: detect via the SYSTEM_PROMPT
    # injected by load_chat_planner (chat_planner.py:15-24) and return a
    # numbered-step list that PlanningOutputParser splits on "\n\d+\. " to
    # build a Plan(steps=[Step(value=...), ...]).
    if "<END_OF_PLAN>" in message_text:
        return (
            "Plan:\n"
            "1. Identify the inputs required to answer the question.\n"
            "2. Look up the relevant facts.\n"
            "3. Given the above steps taken, please respond to the users original question.\n"
            "<END_OF_PLAN>"
        )

    response_format = body.get("response_format") or {}
    if response_format.get("type") != "json_object":
        return "This is a response from the mock server."

    if "Relevance-Judge" in message_text or "Relevance Evaluator" in message_text:
        return json.dumps(
            {
                "explanation": "The response directly answers the user's question and stays fully on topic.",
                "score": 5,
            }
        )

    return json.dumps(
        {
            "explanation": "The response satisfies the evaluator request.",
            "score": 5,
        }
    )


def _stream_chat(body):
    """Yield SSE chunks for an OpenAI streaming chat completion."""
    model = body.get("model", "gpt-4o-mini")
    chunk_id = "chatcmpl-mock-stream-001"

    # role chunk
    yield sse(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
        }
    )

    # content chunks
    for word in ["This ", "is ", "a ", "mock ", "streamed ", "response."]:
        yield sse(
            {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}],
            }
        )

    # usage chunk
    yield sse(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 25,
                "completion_tokens": 6,
                "total_tokens": 31,
            },
        }
    )

    yield "data: [DONE]\n\n"


@bp.route("/v1/chat/completions", methods=["POST"])
@bp.route("/openai/v1/chat/completions", methods=["POST"])
@bp.route("/openai/deployments/<deployment>/chat/completions", methods=["POST"])
@bp.route("/chat/completions", methods=["POST"])
def chat_completions(deployment=None):
    body = request.get_json(silent=True) or {}

    # Streaming
    if body.get("stream"):
        return Response(_stream_chat(body), mimetype="text/event-stream")

    # Compute message text once for content-driven dispatch below.
    message_text = "\n".join(
        message.get("content", "") for message in body.get("messages", []) if isinstance(message.get("content"), str)
    )

    # Tool-call detection: if tools are provided and no tool result yet,
    # return a tool call; otherwise return a normal response (completes the
    # agent loop).
    if body.get("tools"):
        messages = body.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if not has_tool_result:
            resp = copy.deepcopy(CHAT_TOOL_CALL_RESPONSE)
            resp["model"] = body.get("model", resp["model"])
            tool = body.get("tools", [{}])[0]
            tool_name = tool.get("function", {}).get("name")
            if tool_name:
                resp["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = tool_name
            resp["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
                mock_tool_arguments(tool)
            )
            return resp

    # CrewAI planner natural-retry path: when the planner agent's first call
    # uses output_pydantic=PlannerTaskPydanticOutput, CrewAI routes through
    # beta.chat.completions.parse (response_format set in body). When parsed
    # output is None (refusal), _handle_completion falls through to a plain
    # chat.completions.create with the same params (without response_format).
    # If that returns text, CrewAI's Task._export_output -> convert_to_model
    # routes through handle_partial_json -> convert_with_instructions which
    # builds a Converter that issues a third LLM call with the schema-
    # conversion system prompt ("Format your final answer ..."). Three real
    # LLM round-trips through CrewAI's NATURAL agent flow, all under one
    # plan span. The [FORCE_PLANNER_MULTI_CALL] sentinel scopes the malformed
    # behavior to this scenario only; other crewai paths see the standard
    # planner branch below.
    if (
        "[FORCE_PLANNER_MULTI_CALL]" in message_text
        and "Task Execution Planner" in message_text
        and body.get("response_format")
    ):
        # First call: beta.parse path -- return refusal so parsed_object=None
        # and CrewAI falls through to the regular create() path.
        resp = copy.deepcopy(CHAT_REFUSAL_RESPONSE)
        resp["model"] = body.get("model", resp["model"])
        return resp

    if (
        "[FORCE_PLANNER_MULTI_CALL]" in message_text
        and "Task Execution Planner" in message_text
        and not body.get("response_format")
    ):
        # Second call: fall-through create() with NO response_format. Return
        # text the converter will fail to validate as PlannerTaskPydanticOutput,
        # which forces convert_to_model -> handle_partial_json ->
        # convert_with_instructions and a third LLM round-trip.
        resp = copy.deepcopy(CHAT_RESPONSE)
        resp["model"] = body.get("model", resp["model"])
        resp["choices"] = copy.deepcopy(resp["choices"])
        resp["choices"][0]["message"]["content"] = "I drafted this plan but it is not in the requested schema."
        return resp

    resp = dict(CHAT_RESPONSE)
    resp["model"] = body.get("model", resp["model"])
    resp["choices"] = copy.deepcopy(resp["choices"])
    resp["choices"][0]["message"]["content"] = _mock_chat_content(body, message_text)
    return resp


@bp.route("/v1/embeddings", methods=["POST"])
@bp.route("/openai/v1/embeddings", methods=["POST"])
@bp.route("/openai/deployments/<deployment>/embeddings", methods=["POST"])
@bp.route("/embeddings", methods=["POST"])
def embeddings(deployment=None):
    body = request.get_json(silent=True) or {}
    resp = dict(EMBEDDING_RESPONSE)
    resp["model"] = body.get("model", resp["model"])
    return resp


@bp.route("/v1/responses", methods=["POST"])
@bp.route("/openai/v1/responses", methods=["POST"])
def responses():
    body = request.get_json(silent=True) or {}
    resp = dict(RESPONSES_RESPONSE)
    resp["model"] = body.get("model", resp["model"])
    return resp
