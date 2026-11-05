"""Verify committed exception events survive loading for reports."""

from semconv_genai.data_files import load_scenario_data_files


def test_committed_openai_exception_events_round_trip():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    assert entries["openai"].events["gen_ai.client.inference.exception"] == {
        "exception.message": "present",
        "exception.stacktrace": "present",
        "exception.type": "present",
    }


if __name__ == "__main__":
    test_committed_openai_exception_events_round_trip()
    print("ok")
