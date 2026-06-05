"""AWS Bedrock Agent Runtime-compatible endpoints."""

import base64
import json

from flask import Blueprint, Response, request

from ._common import encode_aws_event_stream_message

bp = Blueprint("bedrock_agent", __name__)


def _stream_invoke(agent_id, alias_id, session_id, enable_trace=False):
    """Yield Bedrock Agent invoke_agent event-stream chunks in binary format."""
    events = []
    # The agent response is delivered as chunk events with base64-encoded bytes
    text = "This is a response from the mock server."
    events.append(("chunk", {"bytes": base64.b64encode(text.encode("utf-8")).decode("ascii")}))
    if enable_trace:
        events.append(
            (
                "trace",
                {
                    "agentId": agent_id,
                    "agentAliasId": alias_id,
                    "agentVersion": "1",
                    "sessionId": session_id,
                    "eventTime": "2026-04-08T00:00:00Z",
                    "trace": {
                        "customOrchestrationTrace": {
                            "traceId": "trace-mock-001",
                            "event": {
                                "text": "Mock orchestration trace",
                            },
                        }
                    },
                },
            )
        )
    for event_type, body in events:
        payload = json.dumps(body).encode("utf-8")
        yield encode_aws_event_stream_message(event_type, payload)


@bp.route("/agents/<agent_id>/agentAliases/<alias_id>/sessions/<session_id>/text", methods=["POST"])
def bedrock_agent_invoke(agent_id, alias_id, session_id):
    """Handle Bedrock Agent Runtime InvokeAgent."""
    body = request.get_json(silent=True) or {}
    return Response(
        _stream_invoke(
            agent_id,
            alias_id,
            session_id,
            enable_trace=bool(body.get("enableTrace")),
        ),
        mimetype="application/vnd.amazon.eventstream",
        headers={
            "x-amzn-bedrock-agent-session-id": session_id,
            "x-amz-bedrock-agent-content-type": "application/json",
        },
    )
