"""Reference implementation for mem0 memory operations."""

import os
import tempfile
from pathlib import Path

from reference_shared import flush_and_shutdown, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

USER_ID = "test-user"
MEMORY_TEXT = "User prefers vegetarian meals and dark mode."
QUERY_TEXT = "vegetarian meal preference"


def run_memory_reference():
    """Scenario: mem0 add/search with first-party OpenTelemetry spans."""
    print("  [memory] mem0 add and search")

    os.environ["MEM0_TELEMETRY"] = "false"
    os.environ["OPENAI_API_KEY"] = "mock-key"
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

    from mem0 import Memory

    with tempfile.TemporaryDirectory(prefix="mem0-reference-") as storage_dir:
        storage_path = Path(storage_dir)
        memory = Memory.from_config(
            {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "mem0-reference",
                        "embedding_model_dims": 256,
                        "path": str(storage_path / "qdrant"),
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "api_key": "mock-key",
                        "openai_base_url": MOCK_BASE_URL,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": "mock-key",
                        "embedding_dims": 256,
                        "openai_base_url": MOCK_BASE_URL,
                    },
                },
                "history_db_path": str(storage_path / "history.db"),
            }
        )

        add_result = memory.add(MEMORY_TEXT, user_id=USER_ID)
        assert len(add_result["results"]) == 1

        search_result = memory.search(QUERY_TEXT, filters={"user_id": USER_ID})
        assert len(search_result["results"]) == 1


def main():
    print("=== Reference Implementation: mem0 Memory ===")
    tracer_provider, logger_provider, meter_provider = setup_otel()

    run_memory_reference()

    flush_and_shutdown(tracer_provider, logger_provider, meter_provider)


if __name__ == "__main__":
    main()
