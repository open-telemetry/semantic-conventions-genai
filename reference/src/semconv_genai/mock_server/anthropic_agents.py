"""Anthropic Managed Agents-compatible endpoints (agent creation)."""

import json

from flask import Blueprint, Response, request

bp = Blueprint("anthropic_agents", __name__)

_TIMESTAMP = "2026-04-08T00:00:00Z"

# In-memory state keyed by id.
_AGENTS: dict[str, dict] = {}


def _json(body, status=200):
    return Response(json.dumps(body), status=status, mimetype="application/json")


def _next_id(prefix, store):
    return f"{prefix}_mock_{len(store) + 1:03d}"


@bp.route("/v1/agents", methods=["POST"])
def create_agent():
    body = request.get_json(silent=True) or {}
    agent_id = _next_id("agent", _AGENTS)
    model = body.get("model")
    agent = {
        "id": agent_id,
        "type": "agent",
        "name": body.get("name", "unnamed-agent"),
        "description": body.get("description"),
        "system": body.get("system"),
        "model": model if isinstance(model, dict) else {"id": model},
        "tools": body.get("tools", []),
        "skills": body.get("skills", []),
        "mcp_servers": body.get("mcp_servers", []),
        "multiagent": None,
        "metadata": body.get("metadata", {}),
        "version": 1,
        "created_at": _TIMESTAMP,
        "updated_at": _TIMESTAMP,
        "archived_at": None,
    }
    _AGENTS[agent_id] = agent
    return _json(agent)
