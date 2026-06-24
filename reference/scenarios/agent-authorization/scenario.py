"""Reference implementation for an agent-authorization producer.

Exercises the ``gen_ai.agent.*`` authorization attributes added in #291. The
producer is a trust / authorization control plane that, at the agent-invocation
decision point, emits the agent's identity-key algorithm, its producer-scoped
trust and drift scores together with the method token that produced each, and
the most recent security-scan verdict with its method token. It then lets the
authorized agent run one inference against the mock OpenAI server.

These attributes are producer-emitted decision inputs. They are not read from
the LLM SDK request or response, so each is bound to a local at the decision
point and set inline on the ``invoke_agent`` span -- the signal these
attributes appear on. The score / verdict values travel with their ``.method``
token so a consumer can tell a change in the scoring or scanning method from a
change in the agent's behaviour.
"""

import json
import os

from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_agent_authorization_reference(client):
    """Scenario: an authorized agent invocation annotated with producer trust attributes."""
    print("  [invoke_agent] authorized agent invocation with producer trust attributes")
    request_model = "gpt-4o-mini"
    agent_id = "asst_5j66UpCpwteGg4YSxUnt7lPY"
    agent_name = "Research Assistant"

    # Producer-emitted decision inputs. The authorization control plane computes
    # these at decision time; they do not come from the LLM SDK call below.
    # Each score / verdict is paired with the method token that produced it.
    agent_capability = "database.read"
    public_key_algorithm = "ed25519"
    trust_score = 0.93
    trust_method = "trust-model@2.3.1"
    drift_score = 0.04
    drift_method = "embedding-cosine@1.4"
    scan_verdict = "clean"
    scan_method = "scanner@1.2.0"

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
        # Authorization decision inputs, emitted by the producer on the
        # agent-invocation span before the agent acts.
        span.set_attribute("gen_ai.agent.capability", agent_capability)
        span.set_attribute("gen_ai.agent.public_key.algorithm", public_key_algorithm)
        span.set_attribute("gen_ai.agent.trust.score", trust_score)
        span.set_attribute("gen_ai.agent.trust.method", trust_method)
        span.set_attribute("gen_ai.agent.drift.score", drift_score)
        span.set_attribute("gen_ai.agent.drift.method", drift_method)
        span.set_attribute("gen_ai.agent.scan.verdict", scan_verdict)
        span.set_attribute("gen_ai.agent.scan.method", scan_method)

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

    run_agent_authorization_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
