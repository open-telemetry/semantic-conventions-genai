"""Reference implementation for LangChain retrieval, planning, and workflow (LangGraph) runs."""

import asyncio
import json
import os
from typing import TypedDict

from langchain_core.tools import tool
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

AGENT_MODEL = "gpt-4o-mini"
AGENT_NAME = "weather-agent"
AGENT_SYSTEM_PROMPT = "You are a helpful weather assistant."

_reference_tracer = reference_tracer()


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"Sunny, 72°F in {location}"


class GraphState(TypedDict):
    messages: list[str]


async def agent_node(state: GraphState) -> GraphState:
    """Graph node that delegates to a LangGraph agent, reported as an invoke_agent span."""
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    agent = create_agent(
        model=ChatOpenAI(model=AGENT_MODEL, base_url=MOCK_BASE_URL, api_key="mock-key"),
        tools=[get_weather],
        system_prompt=AGENT_SYSTEM_PROMPT,
        name=AGENT_NAME,
    )

    input_text = state["messages"][-1]
    agent_span_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": AGENT_NAME,
        "gen_ai.request.model": AGENT_MODEL,
    }
    with _reference_tracer.start_as_current_span(
        f"invoke_agent {AGENT_NAME}", attributes=agent_span_attributes
    ) as agent_span:
        agent_span.set_attribute(
            "gen_ai.system_instructions", json.dumps([{"type": "text", "content": AGENT_SYSTEM_PROMPT}])
        )
        agent_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )
        agent_span.set_attribute(
            "gen_ai.tool.definitions",
            json.dumps([{"type": "function", "name": get_weather.name, "description": get_weather.description}]),
        )

        # LangChain delegates the model call to the underlying LLM client (openai),
        # whose own instrumentation owns the inference span. The agent runs the tool
        # itself, so the execute_tool span belongs to LangChain instrumentation.
        result = await agent.ainvoke({"messages": [{"role": "user", "content": input_text}]})

        final_message = result["messages"][-1]
        usage = getattr(final_message, "usage_metadata", None) or {}
        if usage.get("input_tokens"):
            agent_span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
        if usage.get("output_tokens"):
            agent_span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
        agent_span.set_attribute(
            "gen_ai.output.messages",
            json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": final_message.text()}]}]),
        )
        return {"messages": state["messages"] + [final_message.text()]}


def format_node(state: GraphState) -> GraphState:
    print("  [format] formatting agent result")
    last_message = state["messages"][-1]
    return {"messages": state["messages"] + [f"Weather report: {last_message}"]}


def run_retrieval_reference():
    """Scenario: in-memory retrieval via LangChain retriever with reference implementation."""
    print("  [retrieval] in-memory retrieval (reference implementation)")
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever

    class WeatherRetriever(BaseRetriever):
        docs: list[Document]
        top_k: int = 2

        def _get_relevant_documents(self, query: str):
            query_lower = query.lower()
            matches = [doc for doc in self.docs if query_lower.split()[0] in doc.page_content.lower()]
            return matches[: self.top_k]

    data_source_id = "weather-knowledge-base"
    query_text = "Seattle weather"
    top_k = 2
    retriever = WeatherRetriever(
        docs=[
            Document(page_content="Seattle weather is rainy and cool.", metadata={"source_id": data_source_id}),
            Document(page_content="Paris weather is mild and breezy.", metadata={"source_id": data_source_id}),
        ],
        top_k=top_k,
    )

    with _reference_tracer.start_as_current_span("retrieval weather-knowledge-base") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", data_source_id)
        span.set_attribute("gen_ai.retrieval.top_k", top_k)
        span.set_attribute("gen_ai.retrieval.query.text", query_text)
        documents = retriever.invoke(query_text)
        span.set_attribute(
            "gen_ai.retrieval.documents",
            json.dumps(
                [
                    {
                        "content": document.page_content,
                        "source_id": document.metadata.get("source_id"),
                    }
                    for document in documents
                ]
            ),
        )
        print(f"    -> {documents[0].page_content[:60]}")


def run_plan_and_execute_reference():
    """Scenario: agent planning phase via langchain-experimental Plan-and-Execute.

    `langchain_experimental.plan_and_execute.load_chat_planner(llm)` returns
    an `LLMPlanner` whose `.plan(inputs)` issues a single LLM call instructed
    by `SYSTEM_PROMPT` (chat_planner.py:15-24, ending with "<END_OF_PLAN>")
    and parses the response into `Plan(steps=[Step(value=...), ...])` via
    `PlanningOutputParser`. The mock server detects the `"<END_OF_PLAN>"`
    marker and returns a numbered-step body that the parser splits into
    `Step` objects deterministically.

    The plan span represents the planning phase. The LLM call that generates
    the plan is issued by `langchain_openai.ChatOpenAI` (backed by the `openai`
    client) and is captured as a child inference span by generic OpenAI
    instrumentation, so this reference scenario does not emit it.
    """
    print("  [plan] Plan-and-Execute via langchain-experimental (reference implementation)")
    from langchain_experimental.plan_and_execute import load_chat_planner
    from langchain_openai import ChatOpenAI

    request_model = "gpt-4o-mini"
    chat_model = ChatOpenAI(
        model=request_model,
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    planner = load_chat_planner(chat_model)
    planner_input = "What is the capital of France?"

    # langchain-experimental's LLMPlanner has no library-owned agent identity
    # or name (no .id, no .name) -- the planner is a thin wrapper over an
    # LLMChain. Per evaluate-reference rubric, omit gen_ai.agent.id /
    # gen_ai.agent.name rather than emitting opaque object addresses or the
    # implementation class name.
    with _reference_tracer.start_as_current_span("plan") as plan_span:
        plan_span.set_attribute("gen_ai.operation.name", "plan")
        plan = planner.plan(inputs={"input": planner_input})
        print(f"    -> planned {len(plan.steps)} step(s)")


def run_execute_tool_reference():
    """Scenario: tool execution via LangChain's tool runner.

    The model call that produces the tool call is issued by
    `langchain_openai.ChatOpenAI` (backed by the `openai` client) and is captured
    as an inference span by generic OpenAI instrumentation, so it is not emitted
    here. Running the tool is LangChain's own work: `BaseTool.invoke()` executes
    the function and builds the `ToolMessage`, so that is where generic LangChain
    instrumentation produces the execute_tool span.
    """
    print("  [execute_tool] tool execution via LangChain tool runner (reference implementation)")
    from langchain_openai import ChatOpenAI

    chat_model = ChatOpenAI(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    ).bind_tools([get_weather])

    response = chat_model.invoke("What's the weather in Seattle?")
    if not response.tool_calls:
        print("    -> no tool call returned")
        return

    tool_call = response.tool_calls[0]
    tool_span_attributes = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": get_weather.name,
        "gen_ai.tool.description": get_weather.description,
        "gen_ai.tool.type": "function",
    }
    with _reference_tracer.start_as_current_span(
        f"execute_tool {get_weather.name}", attributes=tool_span_attributes
    ) as tool_span:
        tool_span.set_attribute("gen_ai.tool.call.id", tool_call["id"])
        tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps(tool_call["args"]))
        tool_message = get_weather.invoke(tool_call)
        tool_span.set_attribute("gen_ai.tool.call.result", tool_message.content)
    print(f"    -> {tool_message.content[:60]}")


async def run_workflow_reference():
    """Scenario: graph execution via LangGraph wrapped in a workflow span."""
    print("  [workflow] LangGraph graph run (reference implementation)")
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(GraphState)
    builder.add_node("agent", agent_node)
    builder.add_node("format", format_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", "format")
    builder.add_edge("format", END)

    graph = builder.compile()

    input_text = "What's the weather in Seattle?"
    workflow_name = "Weather graph"
    workflow_span_attributes = {
        "gen_ai.operation.name": "invoke_workflow",
    }
    with _reference_tracer.start_as_current_span(
        f"invoke_workflow {workflow_name}", attributes=workflow_span_attributes
    ) as workflow_span:
        workflow_span.set_attribute("gen_ai.workflow.name", workflow_name)
        workflow_span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}])
        )

        # The graph coordinates an agent node and a formatting node; the agent
        # invocation is reported as a child invoke_agent span.
        #
        # OpenInference uses the LangChain run_name as the span name:
        # https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-langchain/src/openinference/instrumentation/langchain/_tracer.py#L194
        # Customize run name as documented in LangChain:
        # https://docs.langchain.com/langsmith/trace-with-langchain#customize-run-name
        state = await graph.ainvoke({"messages": [input_text]}, config={"run_name": workflow_name})

        final_output = state["messages"][-1]
        output_messages = json.dumps(
            [
                {
                    "role": "assistant",
                    "parts": [{"type": "text", "content": str(final_output)}],
                }
            ]
        )
        workflow_span.set_attribute("gen_ai.output.messages", output_messages)
        print(f"    -> {final_output[:60]}")


def main():
    print("=== Reference Implementation: LangChain Reference ===")

    tp, lp, mp = setup_otel()
    run_retrieval_reference()
    run_plan_and_execute_reference()
    run_execute_tool_reference()
    asyncio.run(run_workflow_reference())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
