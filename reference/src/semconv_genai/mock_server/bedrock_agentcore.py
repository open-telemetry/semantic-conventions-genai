"""AWS Bedrock AgentCore Memory-compatible endpoints.

Serves both the ``bedrock-agentcore-control`` (control plane) and
``bedrock-agentcore`` (data plane) operations against a single mock URL,
since both boto3 clients accept the same ``endpoint_url``.
"""

import json

from flask import Blueprint, Response, request

bp = Blueprint("bedrock_agentcore", __name__)

# In-memory state keyed by memoryId.
_MEMORIES: dict[str, dict] = {}
_RECORDS: dict[str, list[dict]] = {}
_RECORD_COUNTER = 0


def _next_record_id() -> str:
    """Generate a record id long enough to satisfy SDK validation (>=40 chars)."""
    global _RECORD_COUNTER
    _RECORD_COUNTER += 1
    return f"memrec-mock-{_RECORD_COUNTER:03d}-" + "0" * 24


def _json(body, status=200):
    return Response(json.dumps(body), status=status, mimetype="application/json")


# Control plane -------------------------------------------------------------


@bp.route("/memories/create", methods=["POST"])
def create_memory():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "unnamed-memory")
    memory_id = f"mem-mock-{len(_MEMORIES) + 1:03d}"
    memory = {
        "id": memory_id,
        "arn": f"arn:aws:bedrock-agentcore:us-east-1:123456789012:memory/{memory_id}",
        "name": name,
        "eventExpiryDuration": body.get("eventExpiryDuration", 30),
        "status": "ACTIVE",
        "createdAt": 1735689600.0,
        "updatedAt": 1735689600.0,
    }
    _MEMORIES[memory_id] = memory
    _RECORDS.setdefault(memory_id, [])
    return _json({"memory": memory}, status=201)


@bp.route("/memories/<memory_id>/delete", methods=["DELETE"])
def delete_memory(memory_id):
    if memory_id not in _MEMORIES:
        return _json({"message": f"Memory {memory_id} not found"}, status=404)
    _MEMORIES.pop(memory_id, None)
    _RECORDS.pop(memory_id, None)
    return _json({"memoryId": memory_id, "status": "DELETING"})


# Data plane ----------------------------------------------------------------


@bp.route("/memories/<memory_id>/memoryRecords/batchCreate", methods=["POST"])
def batch_create_memory_records(memory_id):
    if memory_id not in _MEMORIES:
        return _json({"message": f"Memory {memory_id} not found"}, status=404)
    body = request.get_json(silent=True) or {}
    records = body.get("records", [])
    store = _RECORDS[memory_id]
    successful = []
    for rec in records:
        record_id = _next_record_id()
        store.append({"memoryRecordId": record_id, "content": rec.get("content", {})})
        successful.append(
            {
                "memoryRecordId": record_id,
                "status": "SUCCEEDED",
                "requestIdentifier": rec.get("requestIdentifier", ""),
            }
        )
    return _json({"successfulRecords": successful, "failedRecords": []}, status=201)


@bp.route("/memories/<memory_id>/memoryRecords/batchUpdate", methods=["POST"])
def batch_update_memory_records(memory_id):
    if memory_id not in _MEMORIES:
        return _json({"message": f"Memory {memory_id} not found"}, status=404)
    body = request.get_json(silent=True) or {}
    records = body.get("records", [])
    store = _RECORDS[memory_id]
    by_id = {r["memoryRecordId"]: r for r in store}
    successful = []
    failed = []
    for rec in records:
        record_id = rec["memoryRecordId"]
        if record_id in by_id:
            by_id[record_id]["content"] = rec.get("content", by_id[record_id].get("content", {}))
            successful.append({"memoryRecordId": record_id, "status": "SUCCEEDED"})
        else:
            failed.append(
                {
                    "memoryRecordId": record_id,
                    "status": "FAILED",
                    "errorCode": 404,
                    "errorMessage": f"Memory record {record_id} not found",
                }
            )
    return _json({"successfulRecords": successful, "failedRecords": failed})


@bp.route("/memories/<memory_id>/retrieve", methods=["POST"])
def retrieve_memory_records(memory_id):
    if memory_id not in _MEMORIES:
        return _json({"message": f"Memory {memory_id} not found"}, status=404)
    body = request.get_json(silent=True) or {}
    criteria = body.get("searchCriteria", {})
    top_k = criteria.get("topK", 5)
    namespace = body.get("namespace", "/")
    store = _RECORDS[memory_id]
    summaries = []
    for rec in store[-top_k:]:
        summaries.append(
            {
                "memoryRecordId": rec["memoryRecordId"],
                "content": rec.get("content", {}),
                "memoryStrategyId": criteria.get("memoryStrategyId", ""),
                "namespaces": [namespace],
                "createdAt": 1735689600.0,
                "score": 0.93,
                "metadata": rec.get("metadata", {"author": {"stringValue": "assistant"}}),
            }
        )
    return _json({"memoryRecordSummaries": summaries})


@bp.route("/memories/<memory_id>/memoryRecords/<record_id>", methods=["DELETE"])
def delete_memory_record(memory_id, record_id):
    if memory_id not in _MEMORIES:
        return _json({"message": f"Memory {memory_id} not found"}, status=404)
    store = _RECORDS[memory_id]
    if not any(r["memoryRecordId"] == record_id for r in store):
        return _json({"message": f"Memory record {record_id} not found"}, status=404)
    _RECORDS[memory_id] = [r for r in store if r["memoryRecordId"] != record_id]
    return _json({"memoryRecordId": record_id})
