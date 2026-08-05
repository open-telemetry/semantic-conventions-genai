"""Mistral Agents API-compatible endpoints (agent creation).

Mounted under ``/mistral`` because Mistral and Anthropic both serve agent
creation at ``/v1/agents``; the scenario points the SDK's ``server_url`` at the
prefixed base URL.
"""

import json

from flask import Blueprint, Response, request

bp = Blueprint("mistral_agents", __name__, url_prefix="/mistral")

_TIMESTAMP = "2026-04-08T00:00:00Z"

# In-memory state keyed by id.
_AGENTS: dict[str, dict] = {}


def _json(body, status=200):
    return Response(json.dumps(body), status=status, mimetype="application/json")


@bp.route("/v1/agents", methods=["POST"])
def create_agent():
    body = request.get_json(silent=True) or {}
    agent_id = f"ag_mock_{len(_AGENTS) + 1:03d}"
    agent = {
        "id": agent_id,
        "object": "agent",
        "name": body.get("name", "unnamed-agent"),
        "model": body.get("model"),
        "instructions": body.get("instructions"),
        "description": body.get("description"),
        "tools": body.get("tools", []),
        "completion_args": body.get("completion_args"),
        "handoffs": body.get("handoffs"),
        "metadata": body.get("metadata"),
        "version": 0,
        "versions": [0],
        "deployment_chat": False,
        "source": "mistral",
        "created_at": _TIMESTAMP,
        "updated_at": _TIMESTAMP,
    }
    _AGENTS[agent_id] = agent
    return _json(agent)
