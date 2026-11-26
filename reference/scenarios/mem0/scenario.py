"""Reference implementation: mem0 Memory add and search."""

import os
import tempfile

from mem0 import Memory
from opentelemetry.trace import SpanKind
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()

# gen_ai.memory.query.text and gen_ai.memory.records carry content, so they are opt-in.
CAPTURE_CONTENT = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT", "").strip().upper() in (
    "SPAN_ONLY",
    "SPAN_AND_EVENT",
)

USER_ID = "test-user"
MESSAGES = [{"role": "user", "content": "User prefers vegetarian meals and dark mode."}]
QUERY_TEXT = "vegetarian meal preference"
# The mock server returns embeddings of the requested `dimensions`; the vector store must match.
EMBEDDING_DIMS = 256


def _error_type(error):
    return f"{type(error).__module__}.{type(error).__qualname__}"


def build_memory(storage_dir):
    """Create a mem0 Memory on local Qdrant and SQLite that calls the mock server for models."""
    return Memory.from_config(
        {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "mem0-reference",
                    "embedding_model_dims": EMBEDDING_DIMS,
                    "path": os.path.join(storage_dir, "qdrant"),
                },
            },
            "llm": {
                "provider": "openai",
                "config": {"model": "gpt-4o-mini", "api_key": "mock-key", "openai_base_url": MOCK_BASE_URL},
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": "mock-key",
                    "openai_base_url": MOCK_BASE_URL,
                    "embedding_dims": EMBEDDING_DIMS,
                },
            },
            "history_db_path": os.path.join(storage_dir, "history.db"),
        }
    )


def run_create_memory_reference(memory):
    """Scenario: mem0 Memory.add with infer=False."""
    print("  [create_memory] mem0 Memory.add")
    # infer=False stores each message as a new record and skips mem0's LLM fact extraction,
    # which finds no facts in the mock server's reply. So the operation is create_memory.
    # With the default infer=True, mem0 decides what to store, which is upsert_memory.
    with _reference_tracer.start_as_current_span(
        "create_memory", kind=SpanKind.CLIENT, attributes={"gen_ai.operation.name": "create_memory"}
    ) as span:
        # record.count is the attempted creations, known before the call: infer=False stores
        # one record per non-system message.
        span.set_attribute("gen_ai.memory.record.count", sum(message["role"] != "system" for message in MESSAGES))
        try:
            response = memory.add(MESSAGES, user_id=USER_ID, infer=False)
        except Exception as e:
            span.set_attribute("error.type", _error_type(e))
            raise
        results = response["results"]
        if CAPTURE_CONTENT:
            span.set_attribute(
                "gen_ai.memory.records",
                [{"content": result["memory"], "id": result["id"]} for result in results],
            )


def run_search_memory_reference(memory):
    """Scenario: mem0 Memory.search."""
    print("  [search_memory] mem0 Memory.search")
    with _reference_tracer.start_as_current_span(
        "search_memory", kind=SpanKind.CLIENT, attributes={"gen_ai.operation.name": "search_memory"}
    ) as span:
        if CAPTURE_CONTENT:
            span.set_attribute("gen_ai.memory.query.text", QUERY_TEXT)
        try:
            response = memory.search(QUERY_TEXT, filters={"user_id": USER_ID})
        except Exception as e:
            span.set_attribute("error.type", _error_type(e))
            raise
        results = response["results"]
        span.set_attribute("gen_ai.memory.record.count", len(results))
        if CAPTURE_CONTENT:
            span.set_attribute(
                "gen_ai.memory.records",
                [{"content": result["memory"], "id": result["id"], "score": result["score"]} for result in results],
            )


def main():
    print("=== Reference Implementation: mem0 ===")
    tp, lp, mp = setup_otel()

    with tempfile.TemporaryDirectory(prefix="mem0-reference-") as storage_dir, build_memory(storage_dir) as memory:
        run_create_memory_reference(memory)
        run_search_memory_reference(memory)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
