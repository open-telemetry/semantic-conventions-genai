"""Reference implementation for an agent-authorization producer.

Exercises the ``gen_ai.agent.*`` authorization attributes proposed in #180.
These attributes are not properties of the inference call. They are outputs of
the component that makes the authorization decision -- a policy decision point,
an agent gateway, or a control-plane layer sitting in front of the action. That
component already holds the capability being invoked, the agent's identity-key
algorithm, its producer-scoped trust and drift signals, and the most recent
security-scan verdict, because those are the inputs to its allow / deny
decision.

To make both the instrumentation point and the data source explicit, the
scenario models that deciding component as an ``AuthorizationGate`` whose
``decide`` call returns one ``AuthorizationDecision`` object. The instrumentation
sets the span attributes from the fields of that returned decision rather than
from literals, then lets the authorized agent run one inference against the mock
OpenAI server. The signal these attributes appear on is the ``invoke_agent``
span. Each score / verdict travels with its ``.method`` token so a consumer can
tell a change in the scoring or scanning method from a change in the agent's
behaviour.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, ClassVar

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


@dataclass(frozen=True)
class AuthorizationDecision:
    """The result an authorization control plane returns for one agent invocation.

    Each producer-scoped score / verdict is paired with the method token that
    produced it, so a consumer can distinguish a re-fit or re-threshold of the
    method from a real change in the agent.
    """

    allow: bool
    capability: str
    public_key_algorithm: str
    trust_score: float
    trust_method: str
    drift_score: float
    drift_method: str
    scan_verdict: str
    scan_method: str


class AuthorizationGate:
    """Minimal stand-in for the deciding component in front of an agent action.

    A real deployment computes these signals from its own trust model, drift
    detector, and security scanner before allowing the action. This reference
    returns a fixed decision so the scenario stays deterministic; the point it
    demonstrates is structural -- the span attributes are read from the
    returned decision object, not bound at the instrumentation site, so the
    instrumentation point (the gate) and the data source (the decision) are
    both visible.
    """

    # Stands in for the stores a production gate reads: the agent's registered
    # identity key, its current trust and drift scores, and the latest scan
    # verdict. Keyed by agent id so the scenario stays deterministic while the
    # decision is still derived from its input rather than bound at the call.
    _AGENT_RECORDS: ClassVar[dict[str, dict[str, Any]]] = {
        "asst_5j66UpCpwteGg4YSxUnt7lPY": {
            "allow": True,
            "public_key_algorithm": "Ed25519",
            "trust_score": 0.93,
            "trust_method": "trust-model@2.3.1",
            "drift_score": 0.04,
            "drift_method": "embedding-cosine@1.4",
            "scan_verdict": "clean",
            "scan_method": "scanner@1.2.0",
        },
    }

    def decide(self, *, agent_id: str, requested_capability: str) -> AuthorizationDecision:
        # A production decision point resolves the agent's identity key, scores its
        # trust and drift, and reads the latest scan verdict here, then returns them
        # together as the basis for the allow / deny call. Every field below is read
        # from the record for this agent_id, so the input-to-decision flow is visible.
        record = self._AGENT_RECORDS.get(agent_id)
        if record is None:
            raise LookupError(f"no registered record for agent {agent_id}")
        return AuthorizationDecision(
            capability=requested_capability,
            **record,
        )


def run_agent_authorization_reference(client, gate):
    """Scenario: an authorized agent invocation annotated with the gate's decision."""
    print("  [invoke_agent] authorized agent invocation with producer trust attributes")
    request_model = "gpt-4o-mini"
    agent_id = "asst_5j66UpCpwteGg4YSxUnt7lPY"
    agent_name = "Research Assistant"

    # The deciding component runs first and returns its decision. Everything the
    # producer-emitted attributes carry comes from this object, not from the LLM
    # SDK call below.
    decision = gate.decide(agent_id=agent_id, requested_capability="database.read")
    if not decision.allow:
        raise PermissionError(f"authorization gate denied invocation of {agent_id}")

    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": "Summarize the open tasks."},
    ]
    input_messages = json.dumps(
        [{"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]} for m in messages]
    )
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": request_model,
        "gen_ai.agent.id": agent_id,
        "gen_ai.agent.name": agent_name,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(f"invoke_agent {agent_name}", attributes=span_attributes) as span:
        # Signals recorded about the agent, set from the decision the gate returned
        # before the agent acts. Each is a field of `decision`, not a literal.
        span.set_attribute("gen_ai.agent.capability", decision.capability)
        span.set_attribute("gen_ai.agent.public_key.algorithm", decision.public_key_algorithm)
        span.set_attribute("gen_ai.agent.trust.score", decision.trust_score)
        span.set_attribute("gen_ai.agent.trust.method", decision.trust_method)
        span.set_attribute("gen_ai.agent.drift.score", decision.drift_score)
        span.set_attribute("gen_ai.agent.drift.method", decision.drift_method)
        span.set_attribute("gen_ai.agent.scan.verdict", decision.scan_verdict)
        span.set_attribute("gen_ai.agent.scan.method", decision.scan_method)

        span.set_attribute("gen_ai.input.messages", input_messages)
        resp = client.chat.completions.create(model=request_model, messages=messages)
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


def main():
    print("=== Reference Implementation: Agent Authorization Reference Implementation ===")

    tp, lp, mp = setup_otel()

    import openai

    client = openai.OpenAI(base_url=MOCK_BASE_URL, api_key="mock-key")
    gate = AuthorizationGate()

    run_agent_authorization_reference(client, gate)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
