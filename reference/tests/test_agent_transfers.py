"""Regression checks for the committed agent-transfer conformance results."""

import json
import unittest
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


class AgentTransferTests(unittest.TestCase):
    def test_agent_spans_report_finish_reasons(self):
        agents = {
            "google-adk": ("root_agent", "weather_specialist"),
            "openai-agents": ("assistant", "weather-specialist"),
        }
        for library, names in agents.items():
            with self.subTest(library=library):
                data = json.loads((SCENARIOS / library / "data.json").read_text(encoding="utf-8"))
                self.assertIn("gen_ai.response.finish_reasons", data["spans"]["gen_ai.invoke_agent.internal"])
                missing = [
                    finding["message"]
                    for finding in data["findings"]
                    if finding["context"].get("missing_attribute") == "gen_ai.response.finish_reasons"
                    and any(f"invoke_agent {name}'" in finding["message"] for name in names)
                ]
                self.assertEqual(missing, [])

    def test_agent_spans_report_available_token_counts(self):
        agents = {
            "google-adk": ("root_agent", "weather_specialist"),
            "openai-agents": ("assistant", "weather-specialist"),
        }
        for library, names in agents.items():
            data = json.loads((SCENARIOS / library / "data.json").read_text(encoding="utf-8"))
            for attribute in ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"):
                with self.subTest(library=library, attribute=attribute):
                    self.assertIn(attribute, data["spans"]["gen_ai.invoke_agent.internal"])
                    missing = [
                        finding["message"]
                        for finding in data["findings"]
                        if finding["context"].get("missing_attribute") == attribute
                        and any(f"invoke_agent {name}'" in finding["message"] for name in names)
                    ]
                    self.assertEqual(missing, [])

    def test_agent_tool_names_do_not_repeat_the_target(self):
        tools = {
            "google-adk": "weather_specialist",
            "openai-agents": "weather-specialist",
        }
        for library, tool in tools.items():
            with self.subTest(library=library):
                data = json.loads((SCENARIOS / library / "data.json").read_text(encoding="utf-8"))
                duplicate_names = [
                    finding["message"]
                    for finding in data["findings"]
                    if f"execute_tool {tool} {tool}" in finding["message"]
                ]
                self.assertEqual(duplicate_names, [])


if __name__ == "__main__":
    unittest.main()
