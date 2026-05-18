"""Reference implementation for LangChain retrieval and Plan-and-Execute planning."""

import json
import os

from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

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
    request_top_k = 2.0
    retriever = WeatherRetriever(
        docs=[
            Document(page_content="Seattle weather is rainy and cool.", metadata={"source_id": data_source_id}),
            Document(page_content="Paris weather is mild and breezy.", metadata={"source_id": data_source_id}),
        ],
        top_k=2,
    )

    with _reference_tracer.start_as_current_span("retrieval weather-knowledge-base") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", data_source_id)
        span.set_attribute("gen_ai.request.top_k", request_top_k)
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

    The plan span tags the `LLMPlanner` instance as the planning agent. The
    chat child span captures the real outgoing messages from the LLM call
    (patched at `chat_model.root_client.chat.completions.create`, the
    default sync path through `langchain_openai.ChatOpenAI._generate` →
    `self.client.with_raw_response.create(...)`) and the real
    `ChatCompletion` response.
    """
    print("  [plan] Plan-and-Execute via langchain-experimental (reference implementation)")
    from langchain_experimental.plan_and_execute import load_chat_planner
    from langchain_openai import ChatOpenAI

    request_model = "gpt-4o-mini"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    chat_model = ChatOpenAI(
        model=request_model,
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    planner = load_chat_planner(chat_model)
    captured_completion = None
    captured_messages = None

    # langchain-experimental's LLMPlanner has no library-owned agent identity
    # or name (no .id, no .name) -- the planner is a thin wrapper over an
    # LLMChain. Per evaluate-reference rubric, omit gen_ai.agent.id /
    # gen_ai.agent.name rather than emitting opaque object addresses or the
    # implementation class name.
    with _reference_tracer.start_as_current_span("plan") as plan_span:
        plan_span.set_attribute("gen_ai.operation.name", "plan")

        with _reference_tracer.start_as_current_span("chat gpt-4o-mini") as chat_span:
            chat_span.set_attribute("gen_ai.operation.name", "chat")
            chat_span.set_attribute("gen_ai.provider.name", "openai")
            chat_span.set_attribute("gen_ai.request.model", request_model)
            if host:
                chat_span.set_attribute("server.address", host)
            if port is not None:
                chat_span.set_attribute("server.port", port)

            # langchain-openai's ChatOpenAI._generate() goes through
            # self.client.with_raw_response.create(...), where
            # self.client = self.root_client.chat.completions (base.py:1235).
            # Patching root_client.chat.completions.create is the closest
            # capture of the outgoing request and incoming raw response.
            original_create = chat_model.root_client.chat.completions.create

            def _capture_create(*args, **kwargs):
                nonlocal captured_completion, captured_messages
                captured_messages = kwargs.get("messages")
                response = original_create(*args, **kwargs)
                captured_completion = response
                return response

            chat_model.root_client.chat.completions.create = _capture_create
            try:
                plan = planner.plan(inputs={"input": "What is the capital of France?"})
            finally:
                chat_model.root_client.chat.completions.create = original_create

            if captured_messages is not None:
                system_messages = [m for m in captured_messages if m.get("role") == "system"]
                user_messages = [m for m in captured_messages if m.get("role") == "user"]
                if system_messages:
                    chat_span.set_attribute(
                        "gen_ai.system_instructions",
                        json.dumps([{"parts": [{"type": "text", "content": m["content"]}]} for m in system_messages]),
                    )
                if user_messages:
                    chat_span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps(
                            [
                                {"role": "user", "parts": [{"type": "text", "content": m["content"]}]}
                                for m in user_messages
                            ]
                        ),
                    )

            if captured_completion is not None:
                # with_raw_response.create returns an APIResponse wrapping
                # the parsed ChatCompletion; .parse() unwraps it.
                completion = (
                    captured_completion.parse() if hasattr(captured_completion, "parse") else captured_completion
                )
                if getattr(completion, "model", None):
                    chat_span.set_attribute("gen_ai.response.model", completion.model)
                if getattr(completion, "id", None):
                    chat_span.set_attribute("gen_ai.response.id", completion.id)
                if getattr(completion, "choices", None):
                    chat_span.set_attribute(
                        "gen_ai.response.finish_reasons",
                        [choice.finish_reason for choice in completion.choices if choice.finish_reason],
                    )
                    assistant_content = completion.choices[0].message.content
                    if assistant_content:
                        chat_span.set_attribute(
                            "gen_ai.output.messages",
                            json.dumps(
                                [
                                    {
                                        "role": "assistant",
                                        "parts": [{"type": "text", "content": assistant_content}],
                                    }
                                ]
                            ),
                        )
                if getattr(completion, "usage", None):
                    chat_span.set_attribute("gen_ai.usage.input_tokens", completion.usage.prompt_tokens)
                    chat_span.set_attribute("gen_ai.usage.output_tokens", completion.usage.completion_tokens)
            print(f"    -> planned {len(plan.steps)} step(s)")


def main():
    print("=== Reference Implementation: LangChain Reference ===")

    tp, lp, mp = setup_otel()
    run_retrieval_reference()
    run_plan_and_execute_reference()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
