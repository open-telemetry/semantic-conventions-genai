"""Reference implementation for CrewAI.

Exercises: agent task execution, agent planning (CrewPlanner)
against a mock OpenAI server, with manual OTel spans.
"""

import json
import os

from reference_shared import flush_and_shutdown, mock_server_host_port, reference_tracer, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"

_reference_tracer = reference_tracer()


def run_crew():
    """Scenario: basic crew task execution with reference implementation."""
    print("  [crew] basic crew task execution (reference implementation)")
    os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
    os.environ["CREWAI_DISABLE_TRACKING"] = "true"
    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    from crewai import LLM, Agent, Crew, Task
    from crewai.tools import tool

    request_model = "gpt-4o-mini"
    request_choice_count = 2
    request_temperature = 0.2
    request_top_p = 0.9
    request_max_tokens = 64
    request_seed = 7
    request_stop_sequences = ["<END>"]
    request_frequency_penalty = 0.1
    request_presence_penalty = 0.2
    system_prompt = "You are a helpful research assistant."
    host, port = mock_server_host_port(MOCK_BASE_URL)
    os.environ["OPENAI_API_KEY"] = "mock-key"
    os.environ["OPENAI_API_BASE"] = MOCK_BASE_URL
    os.environ["OPENAI_MODEL_NAME"] = request_model
    llm = LLM(
        model=request_model,
        provider="openai",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
        temperature=request_temperature,
        top_p=request_top_p,
        n=request_choice_count,
        max_completion_tokens=request_max_tokens,
        seed=request_seed,
        stop=request_stop_sequences,
        frequency_penalty=request_frequency_penalty,
        presence_penalty=request_presence_penalty,
    )
    captured_completion = None

    @tool
    def get_weather(location: str) -> str:
        """Get the current weather for a location."""
        with _reference_tracer.start_as_current_span("execute_tool get_weather") as tool_span:
            tool_span.set_attribute("gen_ai.operation.name", "execute_tool")
            tool_span.set_attribute("gen_ai.tool.name", "get_weather")
            tool_span.set_attribute("gen_ai.tool.description", get_weather.func.__doc__ or "")
            tool_span.set_attribute("gen_ai.tool.type", "function")
            tool_span.set_attribute(
                "gen_ai.tool.call.arguments",
                json.dumps({"location": location}),
            )
            result = "Sunny, 72°F"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
            return result

    tools = [get_weather]

    researcher_role = "Researcher"
    with _reference_tracer.start_as_current_span("create_agent Researcher") as create_agent_span:
        create_agent_span.set_attribute("gen_ai.operation.name", "create_agent")
        create_agent_span.set_attribute("gen_ai.provider.name", "openai")
        create_agent_span.set_attribute("gen_ai.request.model", request_model)
        if host:
            create_agent_span.set_attribute("server.address", host)
        if port is not None:
            create_agent_span.set_attribute("server.port", port)
        create_agent_span.set_attribute(
            "gen_ai.system_instructions",
            json.dumps([{"parts": [{"type": "text", "content": system_prompt}]}]),
        )
        researcher = Agent(
            role=researcher_role,
            goal="Find information",
            backstory=system_prompt,
            tools=tools,
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )
        create_agent_span.set_attribute("gen_ai.agent.id", str(researcher.id))
        create_agent_span.set_attribute("gen_ai.agent.name", researcher.role)

    task = Task(
        description="Use the get_weather tool to report the weather in Seattle.",
        expected_output="The current weather.",
        agent=researcher,
    )

    crew = Crew(agents=[researcher], tasks=[task], verbose=False)
    workflow_name = getattr(crew, "name", None)

    with _reference_tracer.start_as_current_span("invoke_workflow crew") as workflow_span:
        workflow_span.set_attribute("gen_ai.operation.name", "invoke_workflow")
        if workflow_name:
            workflow_span.set_attribute("gen_ai.workflow.name", workflow_name)
        workflow_span.set_attribute(
            "gen_ai.input.messages",
            json.dumps(
                [
                    {"role": "user", "parts": [{"type": "text", "content": task.description}]},
                ]
            ),
        )

        with _reference_tracer.start_as_current_span("chat gpt-4o-mini") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.provider.name", "openai")
            span.set_attribute("gen_ai.request.model", request_model)
            span.set_attribute("gen_ai.request.choice.count", request_choice_count)
            span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
            span.set_attribute("gen_ai.request.temperature", request_temperature)
            span.set_attribute("gen_ai.request.seed", request_seed)
            span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
            span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
            span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
            span.set_attribute("gen_ai.request.top_p", request_top_p)
            span.set_attribute(
                "gen_ai.system_instructions",
                json.dumps([{"parts": [{"type": "text", "content": system_prompt}]}]),
            )
            span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {"role": "user", "parts": [{"type": "text", "content": task.description}]},
                    ]
                ),
            )
            # CrewAI converts tools to OpenAI function-calling format before
            # passing them to litellm, so we mirror that shape here.
            span.set_attribute(
                "gen_ai.tool.definitions",
                json.dumps(
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.func.__doc__,
                                "parameters": t.args_schema.model_json_schema(),
                            },
                        }
                        for t in tools
                    ]
                ),
            )
            if host:
                span.set_attribute("server.address", host)
            if port is not None:
                span.set_attribute("server.port", port)
            original_create = researcher.llm._client.chat.completions.create

            def _capture_completion(*args, **kwargs):
                nonlocal captured_completion
                response = original_create(*args, **kwargs)
                captured_completion = response
                return response

            researcher.llm._client.chat.completions.create = _capture_completion
            try:
                result = crew.kickoff()
            finally:
                researcher.llm._client.chat.completions.create = original_create
            if captured_completion is not None:
                span.set_attribute("gen_ai.response.model", captured_completion.model)
                span.set_attribute("gen_ai.response.id", captured_completion.id)
                span.set_attribute(
                    "gen_ai.response.finish_reasons",
                    [choice.finish_reason for choice in captured_completion.choices],
                )
                if captured_completion.usage:
                    span.set_attribute("gen_ai.usage.input_tokens", captured_completion.usage.prompt_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", captured_completion.usage.completion_tokens)
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": str(result)}],
                        }
                    ]
                ),
            )
            workflow_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": str(result)}],
                        }
                    ]
                ),
            )
            print(f"    -> {str(result)[:60]}")


def _run_crew_planning_scenario(*, header, task_description):
    """Shared body for the plan-span scenarios.

    The two scenarios (run_crew_planning, run_crew_planning_multi_call)
    differ only by the task description string they pass in: the
    `[FORCE_PLANNER_MULTI_CALL]` sentinel routes the mock through the
    refusal -> fall-through -> converter sequence. Everything else --
    LLM/Agent/Crew construction, plan-span and chat-span wiring,
    teardown -- is identical. Attribute emission stays inline in this
    function so reviewers can see, in one place, exactly what the
    plan-span scenarios emit.
    """
    print(header)
    os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
    os.environ["CREWAI_DISABLE_TRACKING"] = "true"
    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    from crewai import LLM, Agent, Crew, Task
    from crewai.utilities.planning_handler import CrewPlanner

    request_model = "gpt-4o-mini"
    system_prompt = "You are a helpful research assistant."
    host, port = mock_server_host_port(MOCK_BASE_URL)
    os.environ["OPENAI_API_KEY"] = "mock-key"
    os.environ["OPENAI_API_BASE"] = MOCK_BASE_URL
    os.environ["OPENAI_MODEL_NAME"] = request_model
    llm = LLM(
        model=request_model,
        provider="openai",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )

    researcher = Agent(
        role="Researcher",
        goal="Find information",
        backstory=system_prompt,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task = Task(
        description=task_description,
        expected_output="A short summary of forecasting techniques.",
        agent=researcher,
    )

    crew = Crew(
        agents=[researcher],
        tasks=[task],
        planning=True,
        planning_llm=llm,
        verbose=False,
    )

    # Class-level patch on CrewPlanner._handle_crew_planning to open
    # the plan span around it. Patching private CrewPlanner internals
    # is OK; the scenario's entry point is the public
    # Crew(...planning=True).kickoff() below.
    #
    # We pre-build the planner agent (CrewPlanner._create_planning_agent
    # is deterministic and arg-less) so we can record gen_ai.agent.{id,
    # name} on the plan span at creation time, then inject the same
    # instance back via an instance-level override so CrewAI uses the
    # agent whose id we just recorded.
    original_handle = CrewPlanner._handle_crew_planning
    original_create_planning_agent = CrewPlanner._create_planning_agent

    def _wrapped_handle_crew_planning(self):
        planner_agent = original_create_planning_agent(self)
        with _reference_tracer.start_as_current_span(f"plan {planner_agent.role}") as plan_span:
            plan_span.set_attribute("gen_ai.operation.name", "plan")
            plan_span.set_attribute("gen_ai.agent.id", str(planner_agent.id))
            plan_span.set_attribute("gen_ai.agent.name", planner_agent.role)
            self._create_planning_agent = lambda: planner_agent
            try:
                return original_handle(self)
            finally:
                del self._create_planning_agent

    # CrewAI routes the planner's structured-output call through
    # beta.chat.completions.parse (crewai/llms/providers/openai/
    # completion.py around line 1612); fall-through, converter, and
    # worker calls go through chat.completions.create. Wrap both so
    # each LLM round-trip is captured in its own chat span. Calls made
    # while the plan span is active land under it; the worker task call
    # lands as a sibling top-level chat span.
    original_parse = llm._client.beta.chat.completions.parse
    original_create = llm._client.chat.completions.create

    def _emit_chat_span(call_fn, call_args, call_kwargs):
        messages = call_kwargs.get("messages")
        with _reference_tracer.start_as_current_span(f"chat {request_model}") as chat_span:
            chat_span.set_attribute("gen_ai.operation.name", "chat")
            chat_span.set_attribute("gen_ai.provider.name", "openai")
            chat_span.set_attribute("gen_ai.request.model", request_model)
            if host:
                chat_span.set_attribute("server.address", host)
            if port is not None:
                chat_span.set_attribute("server.port", port)

            if messages is not None:
                system_messages = [m for m in messages if m.get("role") == "system"]
                user_messages = [m for m in messages if m.get("role") == "user"]
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

            completion = call_fn(*call_args, **call_kwargs)

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

            return completion

    def _capture_parse(*args, **kwargs):
        return _emit_chat_span(original_parse, args, kwargs)

    def _capture_create(*args, **kwargs):
        return _emit_chat_span(original_create, args, kwargs)

    CrewPlanner._handle_crew_planning = _wrapped_handle_crew_planning
    llm._client.beta.chat.completions.parse = _capture_parse
    llm._client.chat.completions.create = _capture_create
    try:
        result = crew.kickoff()
    finally:
        llm._client.beta.chat.completions.parse = original_parse
        llm._client.chat.completions.create = original_create
        CrewPlanner._handle_crew_planning = original_handle

    print(f"    -> {str(result)[:60]}")


def run_crew_planning():
    """Scenario: agent planning phase via Crew(planning=True).kickoff().

    Uses the public CrewAI entry point: `Crew(..., planning=True,
    planning_llm=llm).kickoff()`. CrewAI's CrewPlanner synthesizes its
    own internal Agent(role="Task Execution Planner", ...) to actually
    run the planning LLM call (see CrewPlanner._create_planning_agent in
    crewai/utilities/planning_handler.py); that planner agent -- not
    the worker agent owning the surrounding tasks -- is what
    `gen_ai.agent.id` and `gen_ai.agent.name` identify on the plan span.

    The plan span and chat-under-plan span are wired in by patching the
    private `CrewPlanner._handle_crew_planning` and
    `CrewPlanner._create_planning_agent` (private patches are fine; the
    entry point stays public). After planning succeeds, `kickoff()` also
    runs the Researcher worker task, which issues an additional LLM
    round-trip; that call is captured as a sibling chat span -- a normal
    inference span that contributes to the crewai inference-span coverage,
    not part of the plan-span demo itself.
    """
    _run_crew_planning_scenario(
        header="  [crew] agent planning phase via Crew(planning=True).kickoff() (reference implementation)",
        task_description="Research the weather forecasting techniques used by meteorologists.",
    )


def run_crew_planning_multi_call():
    """Scenario: planning that exercises CrewAI's natural multi-call path.

    Same public entry point and wiring as `run_crew_planning()`; the
    only difference is the `[FORCE_PLANNER_MULTI_CALL]` sentinel in the
    task description, which routes the mock through three planner-side
    branches in sequence:

    1. The planner's first call uses
       `output_pydantic=PlannerTaskPydanticOutput`, so CrewAI routes it
       through `beta.chat.completions.parse` (response_format set in
       body). The mock returns a refusal payload, which causes
       `_handle_completion` (crewai/llms/providers/openai/completion.py)
       to fall through to a plain `chat.completions.create`.
    2. The fall-through `chat.completions.create` carries the planner's
       prompt with no `response_format`. The mock returns plain text the
       converter cannot validate as `PlannerTaskPydanticOutput`. CrewAI's
       `Task._export_output -> convert_to_model -> handle_partial_json
       -> convert_with_instructions` then constructs a Converter that
       issues a third LLM call.
    3. The Converter's call carries the schema-conversion system prompt
       ("Format your final answer ..."). The mock returns valid Pydantic
       JSON and planning succeeds.

    Three real LLM round-trips for one planning operation, all under
    one plan span via 100% library-native code paths. After planning
    succeeds, `kickoff()` also runs the Researcher worker task (one
    additional LLM round-trip captured as a sibling chat span). The
    sentinel is gated together with "Task Execution Planner" in the
    mock so it never affects the worker agent's chat call.
    """
    _run_crew_planning_scenario(
        header="  [crew] planner natural multi-call fall-through via Crew(planning=True).kickoff() (reference implementation)",
        task_description="[FORCE_PLANNER_MULTI_CALL] Research the weather forecasting techniques used by meteorologists.",
    )


def main():
    print("=== Reference Implementation: CrewAI Reference Implementation ===")

    tp, lp, mp = setup_otel()
    # NO instrument() call - reference implementation only

    run_crew()
    run_crew_planning()
    run_crew_planning_multi_call()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
