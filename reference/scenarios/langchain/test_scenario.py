"""Check that handoff targets are identifiable from LangChain's runtime state."""

import os
import unittest
from unittest.mock import patch

from langchain.agents import AgentState, create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

with patch.dict(os.environ, {"MOCK_LLM_URL": "http://127.0.0.1:9999"}):
    import scenario


class AgentHandoffTargetTests(unittest.TestCase):
    def setUp(self):
        self.agent = create_agent(
            model=ChatOpenAI(model="gpt-4o-mini", api_key="mock-key"),
            tools=[],
            name="weather-specialist",
        )
        builder = StateGraph(AgentState)
        builder.add_node("agent_alias", self.agent)
        builder.add_node("ordinary_node", lambda state: state)
        builder.add_edge(START, "agent_alias")
        builder.add_edge("agent_alias", END)
        builder.add_edge("ordinary_node", END)
        self.graph = builder.compile()

    def resolve(self, command):
        return scenario._agent_handoff_target(command, self.graph)

    def test_resolves_registered_agent_even_when_node_name_differs(self):
        target = self.resolve(Command(graph=Command.PARENT, goto="agent_alias"))
        self.assertIs(target, self.agent)
        self.assertEqual(target.config["metadata"]["lc_agent_name"], "weather-specialist")

    def test_does_not_treat_an_ordinary_node_as_an_agent(self):
        self.assertIsNone(self.resolve(Command(graph=Command.PARENT, goto="ordinary_node")))

    def test_does_not_treat_a_workflow_subgraph_as_an_agent(self):
        builder = StateGraph(AgentState)
        builder.add_node("workflow", self.graph)
        builder.add_edge(START, "workflow")
        builder.add_edge("workflow", END)
        graph = builder.compile()
        self.assertIsNone(scenario._agent_handoff_target(Command(graph=Command.PARENT, goto="workflow"), graph))

    def test_does_not_treat_local_routing_as_a_handoff(self):
        self.assertIsNone(self.resolve(Command(goto="agent_alias")))

    def test_does_not_treat_fanout_as_a_single_agent_handoff(self):
        self.assertIsNone(self.resolve(Command(graph=Command.PARENT, goto=["agent_alias", "ordinary_node"])))

    def test_does_not_resolve_a_missing_node(self):
        self.assertIsNone(self.resolve(Command(graph=Command.PARENT, goto="missing")))

    def test_does_not_treat_arbitrary_values_as_commands(self):
        self.assertIsNone(self.resolve({"graph": Command.PARENT, "goto": "agent_alias"}))


if __name__ == "__main__":
    unittest.main()
