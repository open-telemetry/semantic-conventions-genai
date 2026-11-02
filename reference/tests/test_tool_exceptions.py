"""Check that execute-tool exception handlers cover their entire span."""

import ast
import unittest
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


class ToolExceptionScopeTests(unittest.TestCase):
    def test_exception_handlers_cover_the_entire_tool_span(self):
        libraries = (
            "autogen",
            "crewai",
            "google-adk",
            "google-genai",
            "langchain",
            "llamaindex",
            "openai-agents",
            "pydantic-ai",
            "vertexai",
        )
        for library in libraries:
            tree = ast.parse((SCENARIOS / library / "scenario.py").read_text(encoding="utf-8"))
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            events = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and any(
                    keyword.arg == "event_name"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "gen_ai.execute_tool.exception"
                    for keyword in node.keywords
                )
            ]
            self.assertTrue(events, library)
            for event in events:
                with self.subTest(library=library, line=event.lineno):
                    span = parents[event]
                    while not isinstance(span, ast.With):
                        span = parents[span]
                    self.assertEqual(span.items[0].context_expr.func.attr, "start_as_current_span")
                    self.assertTrue(
                        any(
                            keyword.arg == "record_exception"
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is False
                            for keyword in span.items[0].context_expr.keywords
                        ),
                        "The operation-specific log must not duplicate a default exception event",
                    )
                    self.assertEqual(len(span.body), 1, "Statements outside the handler can fail without a log")
                    handler = span.body[0]
                    self.assertIsInstance(handler, ast.Try)
                    self.assertEqual(len(handler.handlers), 1)
                    exception_handler = handler.handlers[0]
                    self.assertIsInstance(exception_handler.type, ast.Name)
                    self.assertEqual(exception_handler.type.id, "Exception")
                    self.assertIsInstance(exception_handler.body[-1], ast.Raise)
                    self.assertIsNone(exception_handler.body[-1].exc)
                    self.assertEqual(handler.orelse, [])
                    self.assertEqual(handler.finalbody, [])


if __name__ == "__main__":
    unittest.main()
