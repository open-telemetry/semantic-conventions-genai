"""Reference implementation for Azure AI Content Safety."""

import time

from mock_server import content_safety_mock_server
from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_meter,
    reference_tracer,
    setup_otel,
)

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()
_apply_guardrail_duration = _reference_meter.create_histogram(
    "gen_ai.client.apply_guardrail.duration",
    unit="s",
    description="Duration of a remote guardrail operation.",
    explicit_bucket_boundaries_advisory=[
        0.01,
        0.02,
        0.04,
        0.08,
        0.16,
        0.32,
        0.64,
        1.28,
        2.56,
        5.12,
        10.24,
        20.48,
        40.96,
        81.92,
    ],
)


def run_analyze_text_reference():
    """Scenario: Azure analyze_text with provider-native category results."""
    from azure.ai.contentsafety import ContentSafetyClient
    from azure.ai.contentsafety.models import (
        AnalyzeTextOptions,
        AnalyzeTextOutputType,
        TextCategory,
    )
    from azure.core.credentials import AzureKeyCredential

    print("  [apply_guardrail] Azure analyze_text (reference implementation)")
    input_text = "You are an idiot."
    request = AnalyzeTextOptions(
        text=input_text,
        categories=[TextCategory.HATE],
        blocklist_names=["reference-blocklist"],
        output_type=AnalyzeTextOutputType.EIGHT_SEVERITY_LEVELS,
    )

    with content_safety_mock_server() as endpoint:
        client = ContentSafetyClient(
            endpoint=endpoint,
            credential=AzureKeyCredential("mock-key"),
            api_version="2024-09-01",
            retry_total=0,
        )
        host, port = mock_server_host_port(endpoint)
        component_name = type(client).__name__
        span_attributes = {
            "gen_ai.operation.name": "apply_guardrail",
            "gen_ai.provider.name": "azure.ai.content_safety",
            "gen_ai.guardrail.component.name": component_name,
        }
        if host:
            span_attributes["server.address"] = host
        if port is not None:
            span_attributes["server.port"] = port

        start_time = time.perf_counter()
        with _reference_tracer.start_as_current_span(
            f"apply_guardrail {component_name}",
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ):
            response = client.analyze_text(request)

            for category_result in response.categories_analysis:
                category = str(category_result.category)
                severity = category_result.severity
                reference_event_logger().emit(
                    event_name="gen_ai.guardrail.result",
                    body="Guardrail result",
                    attributes={
                        "gen_ai.guardrail.component.name": component_name,
                        "gen_ai.guardrail.content.input.value": request.text,
                        "gen_ai.guardrail.result.type": "severity",
                        "gen_ai.guardrail.result.value": str(severity),
                        "gen_ai.guardrail.risk.category": category,
                        "gen_ai.guardrail.risk.score": float(severity),
                        "gen_ai.provider.name": "azure.ai.content_safety",
                    },
                )

            for blocklist_match in response.blocklists_match:
                reference_event_logger().emit(
                    event_name="gen_ai.guardrail.result",
                    body="Guardrail result",
                    attributes={
                        "gen_ai.guardrail.component.name": component_name,
                        "gen_ai.guardrail.content.input.value": request.text,
                        "gen_ai.guardrail.policy.rule.id": blocklist_match.blocklist_item_id,
                        "gen_ai.guardrail.risk.category": blocklist_match.blocklist_name,
                        "gen_ai.provider.name": "azure.ai.content_safety",
                    },
                )

        _apply_guardrail_duration.record(
            time.perf_counter() - start_time,
            {
                "gen_ai.guardrail.component.name": component_name,
                "gen_ai.provider.name": "azure.ai.content_safety",
            },
        )
        print(f"    -> {category}: severity {severity}")


def main():
    print("=== Reference Implementation: Azure AI Content Safety ===")

    tp, lp, mp = setup_otel()
    run_analyze_text_reference()
    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
