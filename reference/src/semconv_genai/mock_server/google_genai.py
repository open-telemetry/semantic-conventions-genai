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
        "cachedContentTokenCount": 10,
        "candidatesTokenCount": 12,
        "thoughtsTokenCount": 8,
        # total = prompt + candidates + tool_use + thoughts
        "totalTokenCount": 45,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 25}],
        "cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 10}],
        "candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": 12}],
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
        # Tool-use tokens are a separate component of the total, not part of
        # promptTokenCount (see GenerateContentResponseUsageMetadata).
        "toolUsePromptTokenCount": 8,
        "candidatesTokenCount": 12,
        # total = prompt + candidates + tool_use + thoughts
        "totalTokenCount": 45,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 25}],
        "toolUsePromptTokensDetails": [{"modality": "TEXT", "tokenCount": 8}],
        "candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": 12}],
    },
    "modelVersion": "gemini-2.0-flash",
}

FUNCTION_RESPONSE = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"text": "This is a response from the mock server using tools."}],
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 25,
        # Tool-use tokens are a separate component of the total, not part of
        # promptTokenCount (see GenerateContentResponseUsageMetadata).
        "toolUsePromptTokenCount": 8,
        "candidatesTokenCount": 12,
        # total = prompt + candidates + tool_use + thoughts
        "totalTokenCount": 45,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 25}],
        "toolUsePromptTokensDetails": [{"modality": "TEXT", "tokenCount": 8}],
        "candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": 12}],
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

# Per-modality mock token counts, keyed by MIME-type prefix, used to derive a
# realistic per-modality usage breakdown from the request's media parts.
_MIME_MODALITY = (
    ("image/", ("IMAGE", 258)),
    ("audio/", ("AUDIO", 120)),
)

# Mock candidate token counts per generated output modality.
_OUTPUT_MODALITY = {
    "TEXT": 12,
    "IMAGE": 1290,
    "AUDIO": 240,
}


def _request_media_modalities(body):
    """Modalities of non-text media parts in the request, as (modality, token_count)."""
    result = []
    for content in body.get("contents") or []:
        for part in content.get("parts") or []:
            blob = (
                part.get("inlineData") or part.get("inline_data") or part.get("fileData") or part.get("file_data") or {}
            )
            mime = blob.get("mimeType") or blob.get("mime_type") or ""
            for prefix, entry in _MIME_MODALITY:
                if mime.startswith(prefix):
                    result.append(entry)
                    break
    return result


def _response_modalities(body):
    """Requested output modalities (defaults to TEXT)."""
    cfg = body.get("generationConfig") or body.get("generation_config") or {}
    mods = cfg.get("responseModalities") or cfg.get("response_modalities") or []
    return [str(m).upper() for m in mods] or ["TEXT"]


def _multimodal_response(body):
    """Build a response whose usage metadata reflects the request's input/output modalities."""
    # Input: text prompt plus each media part.
    prompt_details = [{"modality": "TEXT", "tokenCount": 25}]
    prompt_details += [{"modality": m, "tokenCount": c} for m, c in _request_media_modalities(body)]
    prompt_total = sum(d["tokenCount"] for d in prompt_details)

    # A portion of each input modality is served from the context cache, so the
    # cache breakdown mirrors the prompt modalities (cached tokens are a subset
    # of the prompt total).
    cache_details = [{"modality": d["modality"], "tokenCount": d["tokenCount"] // 2} for d in prompt_details]
    cache_total = sum(d["tokenCount"] for d in cache_details)

    # Output: one entry per requested response modality.
    out_mods = _response_modalities(body)
    candidate_details = [{"modality": m, "tokenCount": _OUTPUT_MODALITY.get(m, 12)} for m in out_mods]
    candidate_total = sum(d["tokenCount"] for d in candidate_details)

    # Build candidate content parts matching the output modalities.
    parts = []
    for m in out_mods:
        if m == "TEXT":
            parts.append({"text": "The attached media shows a mock scene."})
        elif m == "IMAGE":
            parts.append({"inlineData": {"mimeType": "image/png", "data": "bW9jaw=="}})
        elif m == "AUDIO":
            parts.append({"inlineData": {"mimeType": "audio/wav", "data": "bW9jaw=="}})
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": parts},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": prompt_total,
            "cachedContentTokenCount": cache_total,
            "candidatesTokenCount": candidate_total,
            "totalTokenCount": prompt_total + candidate_total,
            "promptTokensDetails": prompt_details,
            "cacheTokensDetails": cache_details,
            "candidatesTokensDetails": candidate_details,
        },
        "modelVersion": "gemini-2.0-flash",
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


def _has_inline_media(body):
    """True if the request includes non-text media (image/audio/video/document) input."""
    contents = body.get("contents") or []
    for content in contents:
        for part in content.get("parts") or []:
            if any(key in part for key in ("inlineData", "inline_data", "fileData", "file_data")):
                return True
    return False


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
    """Yield a JSON array of chunks for Vertex AI REST streaming."""
    chunks = _stream_chunks()
    yield "["
    for i, chunk in enumerate(chunks):
        if i > 0:
            yield ","
        yield json.dumps(chunk)
    yield "]"


def _stream_sse():
    """Yield SSE-formatted chunks for Vertex AI JS SDK streaming."""
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
    if _has_function_response(body):
        return FUNCTION_RESPONSE
    if body.get("tools"):
        return _tool_response(body)
    if _has_inline_media(body) or set(_response_modalities(body)) != {"TEXT"}:
        return _multimodal_response(body)
    return RESPONSE


@bp.route("/v1beta/agents", methods=["POST"])
def google_genai_agents():
    """Handle Google GenAI Agents API requests."""
    body = request.get_json(silent=True) or {}
    return {
        "name": f"agents/{body.get('name', 'mock-agent-123')}",
        "displayName": body.get("display_name", "test-agent"),
    }


@bp.route("/v1beta/interactions", methods=["POST"])
def google_genai_interactions():
    """Handle Google GenAI Interactions API requests."""
    body = request.get_json(silent=True) or {}
    resp = {
        "id": "interaction-mock-123",
        "model": body.get("model", "gemini-2.0-flash"),
        "status": "COMPLETED",
        "previous_interaction_id": body.get("previous_interaction_id"),
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "text",
                        "text": "This is a response from the mock interactions server.",
                    }
                ],
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "candidates_tokens": 8,
        },
    }
    return resp


@bp.route("/v1/projects/<path:rest>", methods=["POST"])
@bp.route("/v1beta1/projects/<path:rest>", methods=["POST"])
def vertex_ai(rest):
    """Handle Vertex AI API requests (same response format as Google GenAI)."""
    body = request.get_json(silent=True) or {}
    if ":streamGenerateContent" in rest:
        if request.args.get("alt") == "sse":
            return Response(_stream_sse(), mimetype="text/event-stream")
        return Response(_stream_json_array(), mimetype="application/json")
    if ":predict" in rest:
        body = request.get_json(silent=True) or {}
        instances = body.get("instances", [])
        predictions = []
        for _ in instances:
            predictions.append({"embeddings": {"values": [0.001] * 256}})
        return {
            "predictions": predictions,
            "metadata": {"billableCharacterCount": 13},
        }
    if _has_function_response(body):
        return FUNCTION_RESPONSE
    if body.get("tools"):
        return _tool_response(body)
    if _has_inline_media(body) or set(_response_modalities(body)) != {"TEXT"}:
        return _multimodal_response(body)
    return RESPONSE
