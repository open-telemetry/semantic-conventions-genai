"""Verify committed exception events appear in the generated reports."""

import tempfile
import unittest
from pathlib import Path

from semconv_genai.data_files import load_scenario_data_files
from semconv_genai.report import BEGIN_MARKER, END_MARKER, write_status_report


class ExceptionEventReportTests(unittest.TestCase):
    def test_committed_exception_events_appear_in_reports(self):
        entries = {entry.library: entry for entry in load_scenario_data_files()}
        cases = (
            (
                "gen_ai.client.inference.exception",
                "Client Inference Exception",
                "openai",
                "../../docs/gen-ai/client-inference.md#event-gen_aiclientinferenceexception",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "README.md"
            output.write_text(f"{BEGIN_MARKER}\n{END_MARKER}\n", encoding="utf-8")
            write_status_report(output)
            index = output.read_text(encoding="utf-8")
            for event, label, library, doc_link in cases:
                with self.subTest(event=event):
                    self.assertEqual(
                        entries[library].events[event],
                        {
                            "exception.message": "present",
                            "exception.stacktrace": "present",
                            "exception.type": "present",
                        },
                    )
                    filename = event.replace("_", "-").replace(".", "-") + "-event.md"
                    self.assertIn(f"| [{label}](reports/{filename}) | {library} |", index)
                    page = (output.parent / "reports" / filename).read_text(encoding="utf-8")
                    self.assertIn(f"# {label} Event\n", page)
                    self.assertIn(f"[Semantic Convention]({doc_link})", page)
                    for attribute in ("exception.message", "exception.stacktrace", "exception.type"):
                        self.assertIn(f"| {attribute} | [{library}] |", page)


if __name__ == "__main__":
    unittest.main()
