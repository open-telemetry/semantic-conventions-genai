"""Verify committed exception events survive loading for reports."""

from semconv_genai.data_files import load_scenario_data_files


def test_committed_exception_events_round_trip():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    for library, event_name in (
        ("openai", "gen_ai.client.inference.exception"),
        ("openai", "gen_ai.client.embeddings.exception"),
        ("aws-bedrock-agent", "gen_ai.client.invoke_agent.exception"),
    ):
        assert entries[library].events[event_name] == {
            "exception.message": "present",
            "exception.stacktrace": "present",
            "exception.type": "present",
        }


if __name__ == "__main__":
    test_committed_exception_events_round_trip()
    print("ok")
