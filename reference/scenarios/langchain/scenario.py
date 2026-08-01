"""Reference implementation for LangChain retrieval and Plan-and-Execute planning."""

import json
import os

from reference_shared import flush_and_shutdown, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


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


def main():
    print("=== Reference Implementation: LangChain Reference ===")

    tp, lp, mp = setup_otel()
    run_retrieval_reference()
    run_plan_and_execute_reference()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
