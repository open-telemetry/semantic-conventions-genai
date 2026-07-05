"""Google GenAI / Vertex AI -compatible endpoints."""

import copy
import json

from flask import Blueprint, Response, request

from ._common import mock_tool_arguments

bp = Blueprint("google_genai", __name__)


RESPONSE = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"text": "This is a response from the mock server."}],
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 25,
        "candidatesTokenCount": 12,
        "totalTokenCount": 37,
    },
    "modelVersion": "gemini-2.0-flash",
}

FUNCTION_CALL_RESPONSE = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "id": "call_mock_001",
                            "name": "get_weather",
                            "args": {"location": "Seattle"},
                        }
                    }
                ],
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 25,
        "candidatesTokenCount": 12,
        "totalTokenCount": 37,
    },
    "modelVersion": "gemini-2.0-flash",
}

EMBEDDING_RESPONSE = {
    "embedding": {
        "values": [0.001] * 256,
    },
}

BATCH_EMBEDDING_RESPONSE = {
    "embeddings": [
        {"values": [0.001] * 256},
    ],
}


def _has_function_response(body):
    contents = body.get("contents") or []
    for content in contents:
        for part in content.get("parts") or []:
            if "functionResponse" in part or "function_response" in part:
                return True
    return False


def _tool_response(body):
    resp = copy.deepcopy(FUNCTION_CALL_RESPONSE)
    tools = body.get("tools") or []
    function_declarations = []
    if tools:
        tool = tools[0] or {}
        function_declarations = tool.get("functionDeclarations") or tool.get("function_declarations") or []
    if function_declarations:
        declaration = function_declarations[0]
        if declaration.get("name"):
            resp["candidates"][0]["content"]["parts"][0]["functionCall"]["name"] = declaration["name"]
        # Newer google-genai/ADK send the schema as JSON Schema under
        # `parameters_json_schema` (a.k.a. `parametersJsonSchema`) instead of `parameters`.
        parameters = (
            declaration.get("parameters")
            or declaration.get("parameters_json_schema")
            or declaration.get("parametersJsonSchema")
            or {}
        )
        resp["candidates"][0]["content"]["parts"][0]["functionCall"]["args"] = mock_tool_arguments(
            {"function": {"parameters": parameters}}
        )
    return resp


def _stream_chunks():
    """Return the list of streaming chunks for Google GenAI / Vertex AI."""
    chunks = []
    for word in ["This ", "is ", "a ", "mock ", "streamed ", "response."]:
        chunks.append(
            {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": word}]},
                        "index": 0,
                    }
                ],
            }
        )
    chunks.append(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": ""}]},
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 25,
                "candidatesTokenCount": 6,
                "totalTokenCount": 31,
            },
        }
    )
    return chunks


def _stream_ndjson():
    """Yield line-delimited JSON chunks for Google GenAI streaming."""
    for chunk in _stream_chunks():
        yield json.dumps(chunk) + "\n"


def _stream_json_array():
    """Yield a JSON array of chunks for Vertex AI REST streaming.

    The Vertex AI gapic REST transport expects the streaming response body
    to be a JSON array (``[{chunk}, {chunk}, ...]``), not NDJSON.
    """
    chunks = _stream_chunks()
    yield "["
    for i, chunk in enumerate(chunks):
        if i > 0:
            yield ","
        yield json.dumps(chunk)
    yield "]"


def _stream_sse():
    """Yield SSE-formatted chunks for Vertex AI JS SDK streaming.

    The JS ``@google-cloud/vertexai`` SDK requests ``?alt=sse`` and expects
    ``data: <json>\\n\\n`` framing.
    """
    for chunk in _stream_chunks():
        yield f"data: {json.dumps(chunk)}\n\n"


@bp.route("/v1beta/models/<path:model_action>", methods=["POST"])
def google_genai(model_action):
    """Handle Google GenAI API requests (generateContent, streamGenerateContent, embedContent)."""
    body = request.get_json(silent=True) or {}
    if ":streamGenerateContent" in model_action:
        return Response(_stream_ndjson(), mimetype="application/x-ndjson")
    if ":batchEmbedContents" in model_action:
        return BATCH_EMBEDDING_RESPONSE
    if ":embedContent" in model_action:
        return EMBEDDING_RESPONSE
    # :generateContent or any other action
    if body.get("tools") and not _has_function_response(body):
        return _tool_response(body)
    return RESPONSE


@bp.route("/v1/projects/<path:rest>", methods=["POST"])
def vertex_ai(rest):
    """Handle Vertex AI API requests (same response format as Google GenAI)."""
    body = request.get_json(silent=True) or {}
    if ":streamGenerateContent" in rest:
        if request.args.get("alt") == "sse":
            return Response(_stream_sse(), mimetype="text/event-stream")
        return Response(_stream_json_array(), mimetype="application/json")
    if ":predict" in rest:
        # Vertex AI embeddings use the predict endpoint
        body = request.get_json(silent=True) or {}
        instances = body.get("instances", [])
        predictions = []
        for _ in instances:
            predictions.append({"embeddings": {"values": [0.001] * 256}})
        return {
            "predictions": predictions,
            "metadata": {"billableCharacterCount": 13},
        }
    if body.get("tools") and not _has_function_response(body):
        return _tool_response(body)
    return RESPONSE
