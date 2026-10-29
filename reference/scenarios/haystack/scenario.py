"""Reference implementation for Haystack retrieval."""

import json
import time

from opentelemetry.trace import StatusCode
from reference_shared import flush_and_shutdown, reference_meter, reference_tracer, setup_otel

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()
_retrieval_duration = _reference_meter.create_histogram(
    name="gen_ai.retrieval.duration",
    unit="s",
    description="The duration of a single retrieval operation.",
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


def run_retrieval():
    """Scenario: in-memory document retrieval via Haystack with reference implementation."""
    print("  [retrieval] in-memory document retrieval (reference implementation)")
    from haystack import Document
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore

    query_text = "Seattle weather"
    document_store = InMemoryDocumentStore()
    document_store.write_documents(
        [
            Document(content="Seattle weather is rainy and cool."),
            Document(content="Paris weather is mild and breezy."),
            Document(content="London weather is cloudy and damp."),
        ]
    )
    retriever = InMemoryBM25Retriever(document_store=document_store, top_k=2)
    # run() accepts a per-call top_k that overrides the component setting.
    top_k = 1

    metric_attributes = {"gen_ai.operation.name": "retrieval"}
    start_time = time.perf_counter()
    with _reference_tracer.start_as_current_span(
        "retrieval", attributes=metric_attributes, record_exception=False
    ) as span:
        try:
            span.set_attribute("gen_ai.retrieval.top_k", top_k)
            span.set_attribute("gen_ai.retrieval.query.text", query_text)
            result = retriever.run(query=query_text, top_k=top_k)
            documents = result["documents"]
            span.set_attribute(
                "gen_ai.retrieval.documents",
                json.dumps([{"id": document.id, "score": document.score} for document in documents]),
            )
            print(f"    -> {documents[0].content[:60]}")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__qualname__)
            metric_attributes = {**metric_attributes, "error.type": type(e).__qualname__}
            raise
        finally:
            _retrieval_duration.record(time.perf_counter() - start_time, metric_attributes)


def main():
    print("=== Reference Implementation: Haystack Retrieval Reference ===")

    # Pre-load slow haystack modules before connecting OTel to weaver,
    # otherwise weaver's inactivity timeout fires during the long import.
    import haystack  # noqa: F401

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    run_retrieval()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
