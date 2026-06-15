"""Reference implementation for Haystack retrieval."""

import json

from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

_reference_tracer = reference_tracer()


def run_retrieval():
    """Scenario: in-memory document retrieval via Haystack with reference implementation."""
    print("  [retrieval] in-memory document retrieval (reference implementation)")
    from haystack import Document
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore

    data_source_id = "weather-knowledge-base"
    query_text = "Seattle weather"
    top_k = 2
    document_store = InMemoryDocumentStore()
    document_store.write_documents(
        [
            Document(
                content="Seattle weather is rainy and cool.",
                meta={"source_id": data_source_id, "title": "Seattle Weather"},
            ),
            Document(
                content="Paris weather is mild and breezy.",
                meta={"source_id": data_source_id, "title": "Paris Weather"},
            ),
        ]
    )
    retriever = InMemoryBM25Retriever(document_store=document_store, top_k=top_k)

    with _reference_tracer.start_as_current_span("retrieval weather-knowledge-base") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", data_source_id)
        span.set_attribute("gen_ai.retrieval.top_k", top_k)
        span.set_attribute("gen_ai.retrieval.query.text", query_text)
        result = retriever.run(query=query_text)
        documents = result["documents"]
        span.set_attribute(
            "gen_ai.retrieval.documents",
            json.dumps(
                [
                    {
                        "id": getattr(document, "id", None),
                        "content": document.content,
                        "title": document.meta.get("title"),
                        "source_id": document.meta.get("source_id"),
                    }
                    for document in documents
                ]
            ),
        )
        print(f"    -> {documents[0].content[:60]}")


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
