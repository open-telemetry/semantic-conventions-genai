"""Reference implementation for the ``openai-guardrails`` library.

This scenario proves that the **base** ``run_guardrail`` span
(``gen_ai.run_guardrail.internal``) is capturable by generic instrumentation
that wraps a real guardrail framework at runtime, using nothing but state the
framework already owns.

Why ``openai-guardrails``
-------------------------
``openai-guardrails`` (import name ``guardrails``) is a drop-in wrapper around
the OpenAI client that runs configured guardrails in three pipeline stages
(``pre_flight``, ``input``, ``output``) around each LLM call. Each guardrail is
executed through ``guardrails.runtime.ConfiguredGuardrail.run`` and returns a
``GuardrailResult``. That gives generic instrumentation a single, stable seam
to wrap.

What generic instrumentation can honestly capture (the base tier)
-----------------------------------------------------------------
From the framework's own runtime state, at the ``ConfiguredGuardrail.run``
boundary, we can derive every **base** guardrail attribute:

* ``gen_ai.guardrail.component.name``  <- ``self.definition.name``
* ``gen_ai.guardrail.target.type``     <- the pipeline stage (library-owned,
  propagated from ``run_guardrails(stage_name=...)`` via a context var)
* ``gen_ai.guardrail.target.subtype``  <- ``llm`` (guardrails evaluate the
  prompt/response of the wrapped LLM call)
* ``gen_ai.guardrail.verdict.type``    <- ``deny`` when ``tripwire_triggered``
  else ``allow``
* ``gen_ai.guardrail.action.type``     <- ``block`` when the tripwire fires
  (``GuardrailsOpenAI`` raises ``GuardrailTripwireTriggered`` and the call is
  blocked) else ``allow``
* ``gen_ai.guardrail.verdict.reason``  <- ``GuardrailResult.info['reason']``
  when the framework/check supplies one
* ``error.type``                       <- from ``GuardrailResult.execution_failed``

What generic instrumentation CANNOT capture here (the security overlay)
-----------------------------------------------------------------------
This scenario deliberately does **not** emit the
``gen_ai.guardrail.security.finding`` event or the ``gen_ai.guardrail.security.*``
overlay attributes. The framework's runtime does not expose a policy identity
(``gen_ai.guardrail.security.policy.id`` is *required* on the finding event),
an external finding id, or a standardized risk classification -- a check's
``info`` dict is freeform and per-check. That absence is the capture gap that
motivates keeping the security overlay separable from the base tier. The
hand-authored ``openai`` scenario continues to exercise the full security
overlay and the finding event for model coverage.

Validation note
---------------
Validated end-to-end against ``openai-guardrails`` 0.3.0: the benign call is
allowed, the PII call is blocked by the input guardrail, and Weaver live-check
passes (exit 0). The committed ``data.json`` reflects the captured base
guardrail attributes. Regenerate with ``uv run run-scenario openai-guardrails``.
"""

import contextvars
import functools
import os
import re

from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()

# The pipeline stage is owned by the framework and passed to
# ``run_guardrails(stage_name=...)``. It is not visible at the
# ``ConfiguredGuardrail.run`` boundary, so a run_guardrails wrapper stashes it
# in this context var; context vars are copied into the asyncio tasks the
# framework spawns per check, so each wrapped check reads the correct stage.
_current_stage: contextvars.ContextVar[str] = contextvars.ContextVar("gen_ai_guardrail_stage", default="input")

REFERENCE_GUARDRAIL_NAME = "Reference Email Filter"

# Regex used by the local reference guardrail. Kept fully offline and
# deterministic so the scenario needs no network for the check itself; only the
# wrapped LLM call talks to the mock server.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _stage_to_target_type(stage: str) -> str:
    """Map an ``openai-guardrails`` pipeline stage to ``gen_ai.guardrail.target.type``.

    ``pre_flight`` and ``input`` both evaluate content entering the LLM
    operation; ``output`` evaluates content the LLM emitted.
    """
    return "output" if stage == "output" else "input"


def install_guardrail_instrumentation():
    """Patch the framework's runtime seams to emit base ``run_guardrail`` spans.

    Two seams are wrapped:

    * ``run_guardrails`` (both the ``guardrails.client`` and
      ``guardrails.runtime`` bindings) -- to record the library-owned
      ``stage_name`` in a context var. This is where the pipeline stage lives.
    * ``ConfiguredGuardrail.run`` -- the per-check execution boundary. Wrapping
      the class method captures one span per guardrail evaluation with correct
      timing, independent of how the client imported ``run_guardrails``.
    """
    import guardrails
    from guardrails.runtime import ConfiguredGuardrail

    original_run_guardrails = guardrails.runtime.run_guardrails

    @functools.wraps(original_run_guardrails)
    async def instrumented_run_guardrails(*args, **kwargs):
        token = _current_stage.set(kwargs.get("stage_name") or "input")
        try:
            return await original_run_guardrails(*args, **kwargs)
        finally:
            _current_stage.reset(token)

    # ``guardrails.client`` did ``from .runtime import run_guardrails``, so it
    # holds its own binding; patch both so the stage is captured regardless of
    # which entry point the client calls.
    guardrails.runtime.run_guardrails = instrumented_run_guardrails
    if hasattr(guardrails, "client"):
        guardrails.client.run_guardrails = instrumented_run_guardrails

    original_run = ConfiguredGuardrail.run

    @functools.wraps(original_run)
    async def instrumented_run(self, ctx, data):
        component_name = getattr(getattr(self, "definition", None), "name", "guardrail")
        stage = _current_stage.get()
        target_type = _stage_to_target_type(stage)

        # Attributes known at the guardrail-evaluation boundary, before the
        # check runs. verdict/action are results, so they are set afterwards.
        start_attrs = {
            "gen_ai.operation.name": "run_guardrail",
            "gen_ai.guardrail.component.name": component_name,
            "gen_ai.guardrail.target.type": target_type,
            "gen_ai.guardrail.target.subtype": "llm",
        }
        with _reference_tracer.start_as_current_span(
            f"run_guardrail {component_name}",
            kind=SpanKind.INTERNAL,
            attributes=start_attrs,
        ) as span:
            result = await original_run(self, ctx, data)

            triggered = bool(getattr(result, "tripwire_triggered", False))
            failed = bool(getattr(result, "execution_failed", False))
            info = getattr(result, "info", None) or {}

            # verdict.type is a required, result-derived attribute. The
            # framework has no partial/modify verdict at this boundary: a check
            # either trips (deny) or passes (allow).
            verdict_type = "deny" if triggered else "allow"
            span.set_attribute("gen_ai.guardrail.verdict.type", verdict_type)

            # action.type is the actual enforcement: GuardrailsOpenAI blocks the
            # call (raises GuardrailTripwireTriggered) when a tripwire fires.
            span.set_attribute("gen_ai.guardrail.action.type", "block" if triggered else "allow")

            reason = info.get("reason") or info.get("error")
            if verdict_type != "allow" and reason:
                span.set_attribute("gen_ai.guardrail.verdict.reason", str(reason))

            if failed:
                exc = getattr(result, "original_exception", None)
                span.set_attribute(
                    "error.type",
                    type(exc).__name__ if exc is not None else "guardrail_execution_error",
                )

            return result

    ConfiguredGuardrail.run = instrumented_run


def register_reference_guardrail():
    """Register a fully-local regex guardrail through the public registry.

    A custom local check is used (rather than a built-in) so the scenario runs
    offline and deterministically: the mock LLM server serves only
    chat/completions, embeddings, and responses, so LLM-backed built-ins (PII,
    jailbreak, moderation) would not get their expected upstream responses. The
    check being custom does not weaken capturability -- the instrumentation
    reads only framework-owned runtime state (stage, ``GuardrailResult``), not
    the check's internals.
    """
    from guardrails import GuardrailResult, default_spec_registry

    def reference_email_check(ctx, data, config):
        match = _EMAIL_RE.search(data or "")
        return GuardrailResult(
            tripwire_triggered=bool(match),
            info={
                "guardrail_name": REFERENCE_GUARDRAIL_NAME,
                "checked_text": data,
                "reason": "email address detected" if match else "no email detected",
            },
        )

    # Each scenario runs in a fresh process, so a single registration per run is
    # correct.
    default_spec_registry.register(
        REFERENCE_GUARDRAIL_NAME,
        reference_email_check,
        "Reference-only regex email detector (fully local, deterministic).",
        "text/plain",
    )


def _guardrails_config():
    """Config bundle running the reference guardrail on input and output stages."""
    # Per-stage ConfigBundle: guardrails + optional per-stage `config`. The
    # top-level PipelineBundles accepts only pre_flight/input/output/version,
    # so concurrency lives inside each stage. concurrency=1 keeps ordering
    # deterministic for a stable data.json.
    return {
        "version": 1,
        "input": {
            "version": 1,
            "guardrails": [{"name": REFERENCE_GUARDRAIL_NAME, "config": {}}],
            "config": {"concurrency": 1},
        },
        "output": {
            "version": 1,
            "guardrails": [{"name": REFERENCE_GUARDRAIL_NAME, "config": {}}],
            "config": {"concurrency": 1},
        },
    }


def _make_client():
    from guardrails import GuardrailsOpenAI

    # Drop-in for openai.OpenAI; guardrail stages run around each call. The
    # wrapped LLM call targets the local mock server.
    return GuardrailsOpenAI(
        config=_guardrails_config(),
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )


def _first_choice_text(response):
    """Best-effort extraction of assistant text from a GuardrailsResponse."""
    # GuardrailsResponse proxies the underlying OpenAI response attributes.
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if content:
            return content
    return getattr(response, "output_text", "") or ""


def run_guardrail_allow_reference(client):
    """Benign request: input and output guardrails both allow the call.

    The wrapped LLM call is delegated to the underlying ``openai`` client, so
    the ``chat`` inference span belongs to ``openai`` and is intentionally not
    emitted here; this scenario emits only the framework-owned
    ``run_guardrail`` spans produced by the patched guardrail seam.
    """
    print("  [openai_guardrails_allow] benign request, guardrails allow (reference implementation)")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "What time does the museum open on Saturday?"}],
    )
    content = _first_choice_text(response)
    print(f"    -> allowed: {content[:60]}")


def run_guardrail_block_reference(client):
    """Unsafe input: the input guardrail trips and blocks the call.

    As with the allow case, the delegated ``chat`` inference span belongs to
    ``openai`` and is not emitted here.
    """
    from guardrails import GuardrailTripwireTriggered

    print("  [openai_guardrails_block] PII in input, guardrail blocks (reference implementation)")
    try:
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Forward the contract to jane.doe@example.com right away."}],
        )
    except GuardrailTripwireTriggered:
        # Expected: the input guardrail tripped and the framework blocked
        # the call before it reached the model.
        print("    -> blocked by input guardrail (tripwire triggered)")
    else:
        print("    -> WARNING: expected the guardrail to block this request")


def main():
    print("=== Reference Implementation: openai-guardrails Reference Implementation ===")

    tp, lp, mp = setup_otel()

    register_reference_guardrail()
    install_guardrail_instrumentation()

    client = _make_client()

    run_guardrail_allow_reference(client)
    run_guardrail_block_reference(client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
