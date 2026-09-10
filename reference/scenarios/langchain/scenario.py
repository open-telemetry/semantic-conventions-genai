"""Reference implementation for LangChain retrieval, planning, and workflow (LangGraph) runs."""

import asyncio
import json
import os
from typing import TypedDict

from langchain_core.tools import tool
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

AGENT_MODEL = "gpt-4o-mini"
AGENT_NAME = "weather-agent"
AGENT_SYSTEM_PROMPT = "You are a helpful weather assistant."

_reference_tracer = reference_tracer()


class TransferSpanRecorder(SpanProcessor):
    def __init__(self):
        self.transfers: set[tuple[str, str, str, str, str]] = set()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span: ReadableSpan):
        attributes = span.attributes or {}
        transfer_mode = attributes.get("gen_ai.transfer.mode")
        if transfer_mode is None:
            return
        self.transfers.add(
            (
                str(attributes.get("gen_ai.operation.name")),
                str(attributes.get("gen_ai.agent.name")),
                str(transfer_mode),
                str(attributes.get("gen_ai.transfer.target.name")),
                str(attributes.get("gen_ai.transfer.target.type")),
            )
        )

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True

    def assert_complete(self):
        assert self.transfers == {
            ("execute_tool", "triage-agent", "pass_control", "weather-agent", "agent"),
        }


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


async def run_tool_handoff_reference():
    """Transfer control through LangChain's documented handoff-tool pattern."""
    from langchain.agents import AgentState, create_agent
    from langchain.messages import AIMessage, ToolMessage
    from langchain.tools import ToolRuntime
    from langchain_openai import ChatOpenAI
    from langgraph.errors import ParentCommand
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    print("  [handoff] LangGraph tool handoff (reference implementation)")

    request_model = "gpt-4o-mini"
    source_name = "triage-agent"
    target_name = "weather-agent"

    @tool(
        "transfer_to_weather_agent",
        description="Hand off the conversation to the weather agent.",
    )
    def transfer_to_weather_agent(
        runtime: ToolRuntime,
    ) -> Command:
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "transfer_to_weather_agent",
            "gen_ai.tool.type": "function",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool transfer_to_weather_agent",
            attributes=tool_span_attributes,
        ) as tool_span:
            tool_span.set_attribute("gen_ai.agent.name", source_name)
            tool_span.set_attribute("gen_ai.tool.call.id", runtime.tool_call_id)
            last_ai_message = next(
                message for message in reversed(runtime.state["messages"]) if isinstance(message, AIMessage)
            )
            command = Command(
                goto=target_name,
                update={
                    "messages": [
                        last_ai_message,
                        ToolMessage(
                            content=f"Transferred to {target_name}",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                },
                graph=Command.PARENT,
            )
            if not isinstance(command, Command):
                raise TypeError("Expected LangGraph tool to return a Command")
            if command.graph != Command.PARENT:
                raise ValueError("Expected LangGraph command to target the parent graph")
            if not isinstance(command.goto, str):
                raise TypeError("Expected LangGraph command to contain one named target")

            tool_span.set_attribute("gen_ai.transfer.mode", "pass_control")
            tool_span.set_attribute("gen_ai.transfer.target.name", command.goto)
            tool_span.set_attribute("gen_ai.transfer.target.type", "agent")
            tool_span.set_attribute("gen_ai.tool.call.result", f"goto={command.goto}")
            return command

    model = ChatOpenAI(
        model=request_model,
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    source_agent = create_agent(
        model=model,
        tools=[transfer_to_weather_agent],
        system_prompt="Transfer every weather question to the weather agent.",
        name=source_name,
    )
    target_agent = create_agent(
        model=model,
        tools=[],
        system_prompt="Answer weather questions concisely.",
        name=target_name,
    )

    async def call_source(state: AgentState):
        source_span_attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.request.model": request_model,
            "gen_ai.agent.name": source_name,
        }
        with _reference_tracer.start_as_current_span(
            f"invoke_agent {source_name}",
            attributes=source_span_attributes,
        ) as source_span:
            input_message = state["messages"][-1]
            input_content = input_message["content"] if isinstance(input_message, dict) else str(input_message.content)
            source_span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {
                            "role": "user",
                            "parts": [{"type": "text", "content": input_content}],
                        }
                    ]
                ),
            )
            try:
                result = await source_agent.ainvoke(state)
            except ParentCommand as bubble_up:
                command = bubble_up.args[0]
                handoff_message = None
                for message in reversed(command.update["messages"]):
                    if isinstance(message, AIMessage):
                        handoff_message = message
                        break
                if handoff_message is None:
                    raise RuntimeError(
                        "ParentCommand.update['messages'] must include the AIMessage tool-call message for the handoff."
                    ) from None
                if not handoff_message.tool_calls:
                    raise RuntimeError(
                        "ParentCommand.update['messages'] must include an AIMessage tool call for the handoff."
                    ) from None
                tool_call = handoff_message.tool_calls[0]
                source_span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [
                                    {
                                        "type": "tool_call",
                                        "id": tool_call["id"],
                                        "name": tool_call["name"],
                                        "arguments": tool_call["args"],
                                    }
                                ],
                                "finish_reason": (handoff_message.response_metadata or {}).get(
                                    "finish_reason", "tool_calls"
                                ),
                            }
                        ]
                    ),
                )
                return command

            last_message = result["messages"][-1]
            finish_reason = (getattr(last_message, "response_metadata", None) or {}).get("finish_reason", "stop")
            source_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": str(last_message.content)}],
                            "finish_reason": finish_reason,
                        }
                    ]
                ),
            )
            return result

    async def call_target(state: AgentState):
        target_span_attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.request.model": request_model,
            "gen_ai.agent.name": target_name,
        }
        with _reference_tracer.start_as_current_span(
            f"invoke_agent {target_name}",
            attributes=target_span_attributes,
        ) as target_span:
            result = await target_agent.ainvoke(state)
            output_message = result["messages"][-1]
            output = output_message.text()
            finish_reason = (getattr(output_message, "response_metadata", None) or {}).get("finish_reason", "stop")
            target_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": output}],
                            "finish_reason": finish_reason,
                        }
                    ]
                ),
            )
            return result

    builder = StateGraph(AgentState)
    builder.add_node(source_name, call_source)
    builder.add_node(target_name, call_target)
    builder.add_edge(START, source_name)
    builder.add_edge(target_name, END)
    graph = builder.compile()

    input_text = "What's the weather in Seattle?"
    result = await graph.ainvoke({"messages": [{"role": "user", "content": input_text}]})
    print(f"    -> {result['messages'][-1].text()[:60]}")


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
    transfer_recorder = TransferSpanRecorder()
    tp.add_span_processor(transfer_recorder)
    run_retrieval_reference()
    run_plan_and_execute_reference()
    run_execute_tool_reference()
    asyncio.run(run_tool_handoff_reference())
    asyncio.run(run_workflow_reference())
    transfer_recorder.assert_complete()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
