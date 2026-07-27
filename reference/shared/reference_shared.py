"""Shared OTel SDK setup for all Python reference implementation tests."""

import os
from urllib.parse import urlparse

from opentelemetry import metrics, trace
from opentelemetry._logs import get_logger_provider, set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Instrumentation scope name shared by every reference scenario. Emitting
# attribute *names* still happens inline at each call site; only the tracer /
# logger handle itself is centralized here.
GENAI_REFERENCE_INSTRUMENTATION = "gen_ai.reference"


def reference_tracer(name: str = GENAI_REFERENCE_INSTRUMENTATION) -> trace.Tracer:
    """Return the tracer used by reference scenarios to emit gen_ai.* spans."""
    return trace.get_tracer(name)


def reference_event_logger(name: str = GENAI_REFERENCE_INSTRUMENTATION):
    """Return the Logger used by reference scenarios to emit gen_ai.* events."""
    return get_logger_provider().get_logger(name)


def reference_meter(name: str = GENAI_REFERENCE_INSTRUMENTATION) -> metrics.Meter:
    """Return the Meter used by reference scenarios to emit gen_ai.* metrics."""
    return metrics.get_meter(name)


def mock_server_host_port(url: str) -> tuple[str | None, int | None]:
    """Return ``(hostname, port)`` parsed from ``url``.

    Callers set ``server.address`` / ``server.port`` span attributes inline
    using these values; this helper only does the URL parsing. Pass the same
    URL the SDK client connects to (typically the scenario's ``MOCK_BASE_URL``)
    so the connection is visible at the call site.
    """
    parsed = urlparse(url)
    return parsed.hostname, parsed.port


def setup_otel():
    """Configure OTel SDK with OTLP exporters.

    Returns (TracerProvider, LoggerProvider, MeterProvider).
    """
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
    # Empty Resource keeps Weaver live-check focused on the gen_ai.* surface
    # under test. Real apps should set service.name etc.
    resource = Resource.get_empty()

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(tp)

    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True)))
    set_logger_provider(lp)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=5000,
    )
    mp = MeterProvider(
        metric_readers=[reader],
        resource=resource,
        views=[
            View(
                instrument_name="otel.sdk.span.*",
                meter_name="opentelemetry-sdk",
                aggregation=DropAggregation(),
            )
        ],
    )
    metrics.set_meter_provider(mp)

    return tp, lp, mp


def flush_and_shutdown(tp, lp, mp):
    """Flush and shut down all OTel providers."""
    print("Flushing telemetry...")
    tp.force_flush(timeout_millis=5000)
    lp.force_flush(timeout_millis=5000)
    mp.force_flush(timeout_millis=5000)
    tp.shutdown()
    lp.shutdown()
    mp.shutdown()
    print("Done.")
