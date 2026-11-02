"""Check exception coverage of every manual internal agent span."""

import ast
import asyncio
import contextlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
EVENT_NAME = "gen_ai.invoke_agent.exception"


def emits_agent_exception(node):
    return any(isinstance(child, ast.Constant) and child.value == EVENT_NAME for child in ast.walk(node))


class AgentExceptionScopeTests(unittest.TestCase):
    def assert_exception_handler(self, boundary):
        self.assertIsInstance(boundary, ast.Try)
        self.assertEqual(len(boundary.handlers), 1)
        handler = boundary.handlers[0]
        self.assertIsInstance(handler.type, ast.Name)
        self.assertEqual(handler.type.id, "Exception")
        self.assertTrue(emits_agent_exception(handler))
        self.assertIsInstance(handler.body[-1], ast.Raise)
        self.assertIsNone(handler.body[-1].exc)
        self.assertEqual(
            sum(isinstance(child, ast.Constant) and child.value == EVENT_NAME for child in ast.walk(handler)), 1
        )
        self.assertEqual(boundary.orelse, [])
        self.assertEqual(boundary.finalbody, [])

    def test_handlers_cover_entire_current_span_bodies(self):
        counts = {"autogen": 1, "crewai": 1, "google-adk": 4, "langchain": 1, "openai-agents": 4, "pydantic-ai": 1}
        for library, expected_count in counts.items():
            tree = ast.parse((SCENARIOS / library / "scenario.py").read_text(encoding="utf-8"))
            boundaries = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.With):
                    continue
                call = node.items[0].context_expr
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                if call.func.attr != "start_as_current_span":
                    continue
                name = call.args[0]
                prefix = name.values[0] if isinstance(name, ast.JoinedStr) else name
                if isinstance(prefix, ast.Constant) and str(prefix.value).startswith("invoke_agent "):
                    boundaries.append(node)
            self.assertEqual(len(boundaries), expected_count, library)
            for node in boundaries:
                with self.subTest(library=library, line=node.lineno):
                    self.assertEqual(len(node.body), 1, "Preparation and result processing need the same handler")
                    self.assert_exception_handler(node.body[0])
                    self.assertTrue(
                        any(
                            keyword.arg == "record_exception"
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is False
                            for keyword in node.items[0].context_expr.keywords
                        )
                    )

    def test_adk_handoff_finalizes_usage_inside_exception_boundary(self):
        tree = ast.parse((SCENARIOS / "google-adk" / "scenario.py").read_text(encoding="utf-8"))
        run = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "traced_agent_run"
        )
        boundary = next(node for node in run.body if isinstance(node, ast.Try))
        # Ending the span must still run if recording usage or the exception log fails.
        self.assertEqual(len(boundary.finalbody), 1)
        self.assertEqual(ast.unparse(boundary.finalbody[0]), "span.end()")
        handler_only = ast.Try(body=boundary.body, handlers=boundary.handlers, orelse=[], finalbody=[])
        self.assert_exception_handler(handler_only)
        self.assertEqual(len(boundary.body), 1)
        self.assertIsInstance(boundary.body[0], ast.Try)
        usage_attributes = {
            child.value
            for statement in boundary.body[0].finalbody
            for child in ast.walk(statement)
            if isinstance(child, ast.Constant) and str(child.value).startswith("gen_ai.usage.")
        }
        self.assertEqual(usage_attributes, {"gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"})

    def test_langchain_span_handles_preparation_sdk_and_output_failures(self):
        """Run the instrumentation body without importing optional framework dependencies."""
        tree = ast.parse((SCENARIOS / "langchain" / "scenario.py").read_text(encoding="utf-8"))
        run = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "agent_node")
        span_body = next(node for node in run.body if isinstance(node, ast.With))
        function = ast.AsyncFunctionDef(
            name="invoke",
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=[span_body],
            decorator_list=[],
            type_params=[],
        )
        code = compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<agent-span>", "exec")
        for phase in ("preparation", "sdk", "output", "success"):
            with self.subTest(phase=phase):
                error = RuntimeError(f"{phase} failed")
                span = Mock()
                logger = Mock()
                text = Mock(side_effect=error) if phase == "output" else Mock(return_value="Sunny.")
                message = SimpleNamespace(response_metadata={}, usage_metadata={}, text=text)
                invoke = (
                    AsyncMock(side_effect=error) if phase == "sdk" else AsyncMock(return_value={"messages": [message]})
                )
                namespace = {
                    "_reference_tracer": Mock(start_as_current_span=Mock(return_value=contextlib.nullcontext(span))),
                    "agent_span_attributes": {},
                    "AGENT_NAME": "weather-agent",
                    "AGENT_SYSTEM_PROMPT": "Report the weather.",
                    "input_text": "Seattle?",
                    "state": {"messages": ["Seattle?"]},
                    "get_weather": SimpleNamespace(
                        name="get_weather", description=object() if phase == "preparation" else "Get the weather."
                    ),
                    "agent": SimpleNamespace(ainvoke=invoke),
                    "json": json,
                    "StatusCode": SimpleNamespace(ERROR="error"),
                    "SeverityNumber": SimpleNamespace(WARN="warn"),
                    "reference_event_logger": lambda logger=logger: logger,
                }
                exec(code, namespace)
                if phase == "success":
                    self.assertEqual(asyncio.run(namespace["invoke"]()), {"messages": ["Seattle?", "Sunny."]})
                    logger.emit.assert_not_called()
                    span.set_status.assert_not_called()
                    continue
                with self.assertRaises(TypeError if phase == "preparation" else RuntimeError) as raised:
                    asyncio.run(namespace["invoke"]())
                caught = raised.exception
                if phase == "preparation":
                    invoke.assert_not_awaited()
                else:
                    invoke.assert_awaited_once()
                    self.assertIs(caught, error)
                span.set_status.assert_called_once_with("error", str(caught))
                span.set_attribute.assert_any_call(
                    "error.type", f"{type(caught).__module__}.{type(caught).__qualname__}"
                )
                logger.emit.assert_called_once_with(
                    event_name=EVENT_NAME,
                    severity_number="warn",
                    exception=caught,
                )


if __name__ == "__main__":
    unittest.main()
