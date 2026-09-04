"""Reference implementation for Google ADK."""

import asyncio
import contextlib
import json
import os
import pathlib
import shutil
import tempfile
import time

from opentelemetry import trace as _trace
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import StatusCode
from reference_shared import (
    flush_and_shutdown,
    reference_meter,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]
SKILLS_DIR = pathlib.Path(__file__).parent / "skills"
# The `error_code` values ADK returns when a skill tool call named something that
# does not exist. They say which of the call's arguments failed to resolve, which
# is what decides whether that argument may become a metric dimension.
SKILL_UNRESOLVED = frozenset({"SKILL_NOT_FOUND", "REGISTRY_ERROR", "INVALID_ARGUMENTS"})
SCRIPT_UNRESOLVED = frozenset({"SCRIPT_NOT_FOUND", "SCRIPT_NOT_FOUND_FATAL"})

_reference_tracer = reference_tracer()
_reference_meter = reference_meter()

_inference_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.inference_calls",
    unit="{inference_call}",
    description="The number of inference (model) calls a GenAI agent makes during a single invocation.",
)
_tool_calls = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.tool_calls",
    unit="{tool_call}",
    description="The number of tool calls a GenAI agent makes during a single invocation.",
)
_skill_loads = _reference_meter.create_counter(
    "gen_ai.skill.loads",
    unit="{load}",
    description="The number of times a skill was loaded.",
)
_invoke_agent_skill_loads = _reference_meter.create_histogram(
    "gen_ai.invoke_agent.skill.loads",
    unit="{skill}",
    description="The number of skills a GenAI agent activates during a single invocation.",
)
_invoke_workflow_skill_loads = _reference_meter.create_histogram(
    "gen_ai.invoke_workflow.skill.loads",
    unit="{skill}",
    description="The number of skills activated during a single workflow invocation.",
)
_skill_script_executions = _reference_meter.create_counter(
    "gen_ai.skill.script.executions",
    unit="{execution}",
    description="The number of times a skill's script was executed.",
)


class SpanCounter(SpanProcessor):
    """Lightweight span counter for diagnosing whether instrumentation fires."""

    def __init__(self):
        self.count = 0

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        self.count += 1

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True


@contextlib.contextmanager
def _suppress_adk_native_telemetry():
    from google.adk import runners as adk_runners
    from google.adk.agents import base_agent as adk_base_agent
    from google.adk.flows.llm_flows import base_llm_flow as adk_base_llm_flow
    from google.adk.flows.llm_flows import functions as adk_functions
    from google.adk.telemetry import _metrics as adk_metrics
    from google.adk.telemetry import tracing as adk_tracing

    class _DisabledTracer:
        @contextlib.contextmanager
        def start_as_current_span(self, *_args, **_kwargs):
            yield _trace.NonRecordingSpan(_trace.INVALID_SPAN_CONTEXT)

    class _DisabledInstrument:
        def record(self, *_args, **_kwargs):
            pass

    disabled_tracer = _DisabledTracer()
    disabled_instrument = _DisabledInstrument()
    patched_modules = (
        adk_tracing,
        adk_base_agent,
        adk_runners,
        adk_base_llm_flow,
        adk_functions,
    )
    previous_attributes = []

    def patch_attribute(owner, name, value):
        if hasattr(owner, name):
            previous_attributes.append((owner, name, getattr(owner, name)))
            setattr(owner, name, value)

    try:
        for module in patched_modules:
            patch_attribute(module, "tracer", disabled_tracer)
        patch_attribute(adk_tracing.otel_logger, "emit", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_call_llm", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_tool_call", lambda *_args, **_kwargs: None)
        patch_attribute(adk_tracing, "trace_merged_tool_calls", lambda *_args, **_kwargs: None)
        patch_attribute(adk_base_llm_flow, "trace_call_llm", lambda *_args, **_kwargs: None)
        patch_attribute(adk_functions, "trace_tool_call", lambda *_args, **_kwargs: None)
        patch_attribute(adk_functions, "trace_merged_tool_calls", lambda *_args, **_kwargs: None)
        # ADK records gen_ai.client.token.usage and gen_ai.client.operation.duration for the model
        # call it hands to google-genai, but only as a fallback for when no model-client
        # instrumentation is loaded (see tracing._should_emit_native_telemetry). That call belongs
        # to google-genai, so drop those two instruments. Every other ADK instrument is left alone,
        # including the invoke_agent inference/tool call counts, which describe ADK's own work.
        patch_attribute(adk_metrics, "_client_operation_duration", disabled_instrument)
        patch_attribute(adk_metrics, "_client_token_usage", disabled_instrument)
        yield
    finally:
        for owner, name, value in reversed(previous_attributes):
            setattr(owner, name, value)


def run_agent_reference():
    """Scenario: basic agent execution via Google ADK with reference implementation."""
    from google.adk.agents import Agent
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types

    print("  [agent_run] basic ADK agent execution (reference implementation)")

    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")
    request_model = "gemini-2.0-flash"
    input_text = "Say hello."
    request_choice_count = 2
    request_temperature = 0.25
    request_top_p = 0.8
    request_top_k = 5
    request_max_tokens = 96
    request_stop_sequences = ["<END>"]
    request_presence_penalty = 0.4
    request_frequency_penalty = 0.2

    # Per-invocation call counts, scoped to the single agent invocation below.
    # ADK can attribute each inference/tool call to the agent that issued it,
    # which is exactly the criteria the invoke_agent call-count metrics require.
    call_counts = {"inference": 0, "tool": 0}

    def get_weather(location: str, tool_context: ToolContext) -> str:
        """Get the current weather."""
        call_counts["tool"] += 1
        tool_span_attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "get_weather",
            "gen_ai.tool.type": "function",
        }
        with _reference_tracer.start_as_current_span(
            "execute_tool get_weather", attributes=tool_span_attributes
        ) as tool_span:
            tool_span.set_attribute("gen_ai.tool.description", "Get the current weather.")
            tool_span.set_attribute("gen_ai.agent.name", tool_context.agent_name)
            if tool_context.function_call_id:
                tool_span.set_attribute("gen_ai.tool.call.id", tool_context.function_call_id)
            tool_span.set_attribute("gen_ai.tool.call.arguments", json.dumps({"location": location}))
            result = f"Sunny in {location}"
            tool_span.set_attribute("gen_ai.tool.call.result", result)
        return result

    tool_defs = [
        {
            "name": "get_weather",
            "description": "Get the current weather.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "location": {"type": "STRING", "description": "City name"},
                },
                "required": ["location"],
            },
        }
    ]

    with _suppress_adk_native_telemetry():
        agent = Agent(
            name="test_agent",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You are a helpful assistant.",
            tools=[get_weather],
            generate_content_config=types.GenerateContentConfig(
                candidate_count=request_choice_count,
                temperature=request_temperature,
                top_p=request_top_p,
                top_k=request_top_k,
                max_output_tokens=request_max_tokens,
                stop_sequences=request_stop_sequences,
                presence_penalty=request_presence_penalty,
                frequency_penalty=request_frequency_penalty,
            ),
        )

        session_service = InMemorySessionService()
        runner = Runner(agent=agent, app_name="test_app", session_service=session_service)

        async def _run():
            session = await session_service.create_session(
                app_name="test_app",
                user_id="test_user",
            )
            workflow_span_attributes = {
                "gen_ai.operation.name": "invoke_workflow",
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_workflow {runner.app_name}", attributes=workflow_span_attributes
            ) as workflow_span:
                workflow_span.set_attribute("gen_ai.workflow.name", runner.app_name)
                workflow_span.set_attribute("gen_ai.conversation.id", session.id)
                workflow_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                )
                agent_span_attributes = {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.request.model": request_model,
                    "gen_ai.agent.name": agent.name,
                }
                with _reference_tracer.start_as_current_span(
                    "invoke_agent test_agent", attributes=agent_span_attributes
                ) as agent_span:
                    agent_span.set_attribute("gen_ai.request.choice.count", request_choice_count)
                    agent_span.set_attribute("gen_ai.request.max_tokens", request_max_tokens)
                    agent_span.set_attribute("gen_ai.request.temperature", request_temperature)
                    agent_span.set_attribute("gen_ai.request.top_p", request_top_p)
                    agent_span.set_attribute("gen_ai.request.top_k", request_top_k)
                    agent_span.set_attribute("gen_ai.request.frequency_penalty", request_frequency_penalty)
                    agent_span.set_attribute("gen_ai.request.presence_penalty", request_presence_penalty)
                    agent_span.set_attribute("gen_ai.request.stop_sequences", request_stop_sequences)
                    agent_span.set_attribute("gen_ai.conversation.id", session.id)
                    agent_span.set_attribute(
                        "gen_ai.system_instructions",
                        json.dumps([{"type": "text", "content": agent.instruction}]),
                    )
                    agent_span.set_attribute(
                        "gen_ai.input.messages",
                        json.dumps([{"role": "user", "parts": [{"type": "text", "content": input_text}]}]),
                    )
                    agent_span.set_attribute("gen_ai.tool.definitions", json.dumps(tool_defs))
                    usage_metadata = None
                    finish_reason = None
                    last_text = ""
                    async for event in runner.run_async(
                        user_id="test_user",
                        session_id=session.id,
                        new_message=types.Content(
                            role="user",
                            parts=[types.Part(text=input_text)],
                        ),
                    ):
                        if getattr(event, "usage_metadata", None) is not None:
                            # Only model-response events carry usage, so this counts
                            # one inference call per LLM round-trip.
                            call_counts["inference"] += 1
                            usage_metadata = event.usage_metadata
                        event_finish_reason = getattr(event, "finish_reason", None)
                        if isinstance(event, dict):
                            event_finish_reason = event.get("finish_reason")
                        if event_finish_reason is not None:
                            finish_reason = getattr(event_finish_reason, "value", event_finish_reason)
                        if event.content and event.content.parts:
                            text = event.content.parts[0].text
                            if text:
                                last_text = text
                                print(f"    -> {text[:60]}")
                    if usage_metadata is not None:
                        prompt_token_count = getattr(usage_metadata, "prompt_token_count", None)
                        candidate_token_count = getattr(usage_metadata, "candidates_token_count", None)
                        if isinstance(usage_metadata, dict):
                            prompt_token_count = usage_metadata.get("prompt_token_count")
                            candidate_token_count = usage_metadata.get("candidates_token_count")
                        if prompt_token_count is not None:
                            agent_span.set_attribute("gen_ai.usage.input_tokens", prompt_token_count)
                        if candidate_token_count is not None:
                            agent_span.set_attribute("gen_ai.usage.output_tokens", candidate_token_count)
                    if finish_reason is not None:
                        agent_span.set_attribute(
                            "gen_ai.response.finish_reasons",
                            [str(finish_reason).lower()],
                        )
                    if last_text:
                        output_messages = json.dumps(
                            [
                                {
                                    "role": "assistant",
                                    "parts": [{"type": "text", "content": last_text}],
                                }
                            ]
                        )
                        agent_span.set_attribute("gen_ai.output.messages", output_messages)
                        workflow_span.set_attribute("gen_ai.output.messages", output_messages)

        asyncio.run(_run())

        # Both metrics are scoped to the agent invocation and emitted alongside
        # the invoke_agent (internal) span, dimensioned by the agent name.
        metric_attributes = {"gen_ai.agent.name": agent.name}
        _inference_calls.record(call_counts["inference"], metric_attributes)
        _tool_calls.record(call_counts["tool"], metric_attributes)


def run_memory_reference():
    """Scenario: Google ADK memory add/search with reference implementation."""
    from google.adk.events.event import Event
    from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
    from google.adk.sessions.session import Session
    from google.genai import types

    print("  [memory] ADK in-memory memory service (reference implementation)")

    app_name = "test_app"
    user_id = "test_user"
    session_id = "session_memory_1"
    # `derivable`: ADK's InMemoryMemoryService keys its internal store on
    # (app_name, user_id), so this tuple is the library's own scope unit
    # for memory storage and retrieval.
    store_id = f"{app_name}/{user_id}"
    memory_text = "User prefers vegetarian meals and dark mode."
    query_text = "vegetarian meals"

    async def _run():
        # ADK's InMemoryMemoryService has no public store-lifecycle API and
        # produces no store identifier at construction, so create_memory_store
        # is an honest capture gap for this library. The operation is covered
        # by reference/scenarios/aws-bedrock-agentcore/ where the returned
        # memoryId is captured directly.
        memory_service = InMemoryMemoryService()

        event = Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text=memory_text)]),
        )
        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            events=[event],
        )
        memory_records = json.dumps(
            [
                {
                    "content": memory_text,
                    "id": event.id,
                    "metadata": {"author": event.author, "session_id": session.id},
                }
            ]
        )

        upsert_span_attributes = {
            "gen_ai.operation.name": "upsert_memory",
            "gen_ai.memory.store.id": store_id,
        }
        with _reference_tracer.start_as_current_span("upsert_memory", attributes=upsert_span_attributes) as upsert_span:
            upsert_span.set_attribute("gen_ai.memory.record.count", len(session.events))
            upsert_span.set_attribute("gen_ai.memory.records", memory_records)
            await memory_service.add_session_to_memory(session)

        search_span_attributes = {
            "gen_ai.operation.name": "search_memory",
            "gen_ai.memory.store.id": store_id,
        }
        with _reference_tracer.start_as_current_span("search_memory", attributes=search_span_attributes) as search_span:
            search_span.set_attribute("gen_ai.memory.query.text", query_text)
            response = await memory_service.search_memory(
                app_name=app_name,
                user_id=user_id,
                query=query_text,
            )
            search_records = []
            for memory in response.memories:
                content_text = " ".join(part.text for part in memory.content.parts if part.text)
                search_record = {
                    "content": content_text,
                    "metadata": {"author": memory.author},
                }
                if memory.id:
                    search_record["id"] = memory.id
                search_records.append(search_record)
            search_span.set_attribute("gen_ai.memory.record.count", len(search_records))
            search_span.set_attribute("gen_ai.memory.records", json.dumps(search_records))

    asyncio.run(_run())


def _resolved_skill_loads(events):
    """The skills `load_skill` put into context over `events`, with their events.

    Reads ADK session state only. A `load_skill` function call names the skill;
    its function response says whether the name resolved. A call that resolved
    to nothing put no instructions into the context, so it is not a load.
    """
    skill_name_by_call_id = {}
    loads = []
    for event in events:
        parts = event.content.parts if event.content and event.content.parts else []
        for part in parts:
            call = part.function_call
            if call and call.name == "load_skill" and call.id:
                skill_name_by_call_id[call.id] = (call.args or {}).get("skill_name")
            response = part.function_response
            if not response or response.name != "load_skill":
                continue
            skill_name = skill_name_by_call_id.get(response.id)
            payload = response.response or {}
            if not skill_name or payload.get("error_code"):
                # The call named a skill that did not resolve, so no instructions
                # entered the context and there is nothing to report here.
                continue
            loads.append((skill_name, event))
    return loads


def _skills_in_context(events):
    """The skills whose instructions are in context, and whether each is compacted.

    A compaction event's `EventCompaction` (`event.actions.compaction`) declares
    the timestamp range a summary has replaced, so a load whose response event
    falls inside that range is in context in compacted form.
    """
    compacted_ranges = []
    for event in events:
        compaction = event.actions.compaction
        if (
            compaction
            and compaction.start_timestamp is not None
            and compaction.end_timestamp is not None
            and compaction.compacted_content is not None
        ):
            compacted_ranges.append((compaction.start_timestamp, compaction.end_timestamp))

    loaded = {}
    for skill_name, event in _resolved_skill_loads(events):
        loaded[skill_name] = any(start <= event.timestamp <= end for start, end in compacted_ranges)
    return [{"name": name, "compacted": compacted} for name, compacted in loaded.items()]


def run_skills_reference():
    """Scenario: Agent Skills usage via Google ADK's SkillToolset.

    ADK implements the [Agent Skills](https://agentskills.io) lifecycle as a
    toolset: `list_skills` for discovery, `load_skill` for activation, and
    `load_skill_resource` / `run_skill_script` for execution. Every stage runs
    through `BaseTool.run_async`, the same boundary ADK's own
    `record_tool_execution` instruments, so skill telemetry is captured where
    tool execution is captured.

    The model drives every stage: each turn is one `runner.run_async`
    invocation in which ADK's tool loop calls one skill tool. A final phase runs
    the same tools under a `Workflow` graph, where one invocation coordinates
    two agents and the skills it activates span both of them.
    """
    from google.adk.agents import Agent
    from google.adk.apps.app import App, EventsCompactionConfig
    from google.adk.environment import LocalEnvironment
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools import skill_toolset as adk_skill_toolset
    from google.adk.tools.skill_toolset import SkillToolset
    from google.adk.workflow import START, Workflow
    from google.genai import types

    print("  [skills] ADK Agent Skills toolset (reference implementation)")

    os.environ.setdefault("GOOGLE_API_KEY", "mock-key")
    request_model = "gemini-2.0-flash"
    agent_name = "review_agent"
    user_id = "test_user"

    # `direct`: the application hands each skill folder to `load_skill_from_dir`,
    # so the load boundary owns the location the skill came from, and ADK records
    # it on the `Skill` it returns as `_uri`.
    skills = [load_skill_from_dir((SKILLS_DIR / name).resolve()) for name in ("code-review", "pdf-processing")]
    skills_by_name = {skill.name: skill for skill in skills}

    class _TracedSkillTool:
        """Records an `execute_tool` span around `BaseTool.run_async`.

        `run_async` is ADK's own tool-execution entry point — the one its
        `record_tool_execution` hook wraps — so the span covers exactly one
        library call and nothing of the scenario around it.
        """

        async def run_async(self, *, args, tool_context):
            with _reference_tracer.start_as_current_span(
                f"execute_tool {self.name}",
                attributes={
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.tool.name": self.name,
                    "gen_ai.tool.type": "function",
                },
            ) as span:
                span.set_attribute("gen_ai.tool.description", self.description)
                span.set_attribute("gen_ai.agent.name", tool_context.agent_name)
                if tool_context.function_call_id:
                    span.set_attribute("gen_ai.tool.call.id", tool_context.function_call_id)
                span.set_attribute("gen_ai.tool.call.arguments", json.dumps(args))
                # `direct`: the model's function call names the skill it operates on.
                # It is set even when no skill resolves, which is what makes a name
                # the model invented visible.
                skill_name = args.get("skill_name")
                if skill_name:
                    span.set_attribute("gen_ai.skill.name", skill_name)
                # `direct`: the toolset holds the `Skill` the call names, so its
                # frontmatter and the location ADK loaded it from are in hand.
                skill = skills_by_name.get(skill_name)
                if skill is not None:
                    span.set_attribute("gen_ai.skill.description", skill.description)
                    if skill._uri is not None:
                        span.set_attribute("gen_ai.skill.source.uri", skill._uri)
                result = await super().run_async(args=args, tool_context=tool_context)
                span.set_attribute("gen_ai.tool.call.result", json.dumps(result, default=str))
                # `direct`: every skill tool reports a failure as an `error_code` on
                # its result, which is the value ADK's own telemetry hook reads too.
                error_type = result.get("error_code") if isinstance(result, dict) else None
                if error_type:
                    span.set_attribute("error.type", error_type)
                    span.set_status(StatusCode.ERROR, result.get("error", ""))
                self._record_skill_signals(span, args, result, error_type, tool_context)
                return result

        def _record_skill_signals(self, span, args, result, error_type, tool_context):
            """Hook for the per-tool skill attributes and metrics."""

    def _with_enum(declaration, **enums):
        """Narrows declared parameters to the values that exist.

        The base declarations type `skill_name`, `file_path` and `command` as
        open strings. Constraining them to what the toolset actually holds is
        what a deployment does to stop a model inventing names, and it is what
        lets the mock model server choose a resolvable value. Only the
        declaration sent to the model changes; `run_async`, which the telemetry
        reads, stays ADK's own.
        """
        for name, values in enums.items():
            declaration.parameters_json_schema["properties"][name]["enum"] = list(values)
        return declaration

    class _ListSkillsTool(_TracedSkillTool, adk_skill_toolset.ListSkillsTool):
        """Discovery. Operates on no single skill, so it carries no `gen_ai.skill.*`."""

    class _LoadSkillTool(_TracedSkillTool, adk_skill_toolset.LoadSkillTool):
        def __init__(self, toolset, skill_names):
            super().__init__(toolset)
            self.skill_names = skill_names

        def _get_declaration(self):
            return _with_enum(super()._get_declaration(), skill_name=self.skill_names)

        def _record_skill_signals(self, span, args, result, error_type, tool_context):
            # `direct`: ADK names the agent whose turn ran the tool on the call's
            # context, so the dimension holds for a sub-agent of a workflow too.
            attributes = {"gen_ai.agent.name": tool_context.agent_name}
            if error_type:
                attributes["error.type"] = error_type
            # The span carries the name the call asked for either way; the metric
            # takes it only once ADK has resolved it to a skill, so a name the
            # model invented cannot enter the dimension.
            if error_type not in SKILL_UNRESOLVED:
                attributes["gen_ai.skill.name"] = args["skill_name"]
            _skill_loads.add(1, attributes)

    class _LoadSkillResourceTool(_TracedSkillTool, adk_skill_toolset.LoadSkillResourceTool):
        def __init__(self, toolset, skill_names, resource_paths):
            super().__init__(toolset)
            self.skill_names = skill_names
            self.resource_paths = resource_paths

        def _get_declaration(self):
            return _with_enum(
                super()._get_declaration(),
                skill_name=self.skill_names,
                file_path=self.resource_paths,
            )

        def _record_skill_signals(self, span, args, result, error_type, tool_context):
            # `direct`: the resource path is a call argument.
            span.set_attribute("gen_ai.skill.resource.path", args["file_path"])

    class _RunSkillScriptTool(_TracedSkillTool, adk_skill_toolset.RunSkillScriptTool):
        def __init__(self, toolset, skill_names, script_paths, commands):
            super().__init__(toolset)
            self.skill_names = skill_names
            self.script_paths = script_paths
            self.commands = commands

        def _get_declaration(self):
            return _with_enum(
                super()._get_declaration(),
                skill_name=self.skill_names,
                file_path=self.script_paths,
                command=self.commands,
            )

        def _record_skill_signals(self, span, args, result, error_type, tool_context):
            # `direct`: the script path is a call argument.
            script_path = args["file_path"]
            span.set_attribute("gen_ai.skill.script.path", script_path)
            attributes = {"gen_ai.agent.name": tool_context.agent_name}
            if error_type:
                attributes["error.type"] = error_type
            # As above: each argument becomes a metric dimension only once ADK has
            # resolved it. A script that was never found leaves the skill resolved,
            # so the name stays and only the path drops out.
            if error_type not in SKILL_UNRESOLVED:
                attributes["gen_ai.skill.name"] = args["skill_name"]
            if error_type not in SCRIPT_UNRESOLVED:
                attributes["gen_ai.skill.script.path"] = script_path
            # `direct`: the environment reports the status the script exited with.
            # Absent when the tool failed before running anything.
            exit_code = result.get("exit_code") if isinstance(result, dict) else None
            if exit_code is not None:
                span.set_attribute("gen_ai.skill.script.exit_code", exit_code)
                # `derivable`: the low-cardinality form of the exit code above.
                attributes["gen_ai.skill.script.exited_with_error"] = exit_code != 0
            _skill_script_executions.add(1, attributes)

    with _suppress_adk_native_telemetry():
        # An explicit workspace, so the path the skills are materialized under is
        # known before the first call rather than only once a script has run.
        working_dir = pathlib.Path(tempfile.mkdtemp(prefix="adk_skills_"))
        environment = LocalEnvironment(working_dir=working_dir)
        toolset = SkillToolset(skills, environment=environment)
        script_path = "scripts/run_checks.py"
        # The environment materializes the skill's files under the toolset's
        # `skills_folder`, and the toolset's system instruction tells the model to
        # build the command from that path, so this is the command a model call
        # carries.
        script_command = f"python3 {toolset.skills_folder / 'code-review' / script_path}"
        load_skill_tool = _LoadSkillTool(toolset, ["code-review"])
        run_script_tool = _RunSkillScriptTool(toolset, ["code-review"], [script_path], [script_command])
        toolset._tools = [
            _ListSkillsTool(toolset),
            load_skill_tool,
            _LoadSkillResourceTool(toolset, ["code-review"], ["references/review_policy.md"]),
            run_script_tool,
        ]

        agent = Agent(
            name=agent_name,
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You review code changes.",
            tools=[toolset],
        )
        session_service = InMemorySessionService()

        # A two-agent graph for the workflow phase. Each agent holds its own
        # toolset carrying one skill and exposing only `load_skill`, so the
        # skills a workflow invocation activates span more than one agent.
        reviewer_toolset = SkillToolset([skills_by_name["code-review"]], environment=environment)
        reviewer_toolset._tools = [_LoadSkillTool(reviewer_toolset, ["code-review"])]
        reporter_toolset = SkillToolset([skills_by_name["pdf-processing"]], environment=environment)
        reporter_toolset._tools = [_LoadSkillTool(reporter_toolset, ["pdf-processing"])]
        reviewer_agent = Agent(
            name="reviewer_agent",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You review code changes.",
            tools=[reviewer_toolset],
        )
        reporter_agent = Agent(
            name="reporter_agent",
            model=Gemini(model=request_model, base_url=MOCK_BASE_URL),
            instruction="You turn a review into a report.",
            tools=[reporter_toolset],
        )
        # `Workflow` is ADK's graph primitive, and `edges` is how it is defined:
        # the review agent runs from the entry point, the reporting agent after it.
        workflow = Workflow(
            name="code_review_workflow",
            description="Reviews a pending change, then reports on it.",
            edges=[(START, reviewer_agent), (reviewer_agent, reporter_agent)],
        )
        workflow_runner = Runner(
            app=App(name="test_app", root_agent=workflow),
            session_service=session_service,
        )

        def build_runner(compaction_interval=None):
            app = App(
                name="test_app",
                root_agent=agent,
                events_compaction_config=(
                    EventsCompactionConfig(compaction_interval=compaction_interval, overlap_size=0)
                    if compaction_interval
                    else None
                ),
            )
            return Runner(app=app, session_service=session_service)

        async def invoke(runner, session_id, prompt, tool_name=None):
            """One agent invocation, wrapped in its `invoke_agent` span.

            Exposing a single skill tool for the turn is what makes the model's
            choice deterministic; the call itself, its arguments and its
            execution are all ADK's. A turn that names no tool exposes none, so
            the model answers with text. The filter is a predicate rather than an
            empty list, which ADK reads as *no filter* and would expose all four.
            """
            toolset.tool_filter = [tool_name] if tool_name else lambda tool, readonly_context=None: False
            before = await session_service.get_session(app_name="test_app", user_id=user_id, session_id=session_id)
            events_before = len(before.events)
            agent_span_attributes = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.request.model": request_model,
                "gen_ai.agent.name": agent_name,
            }
            with _reference_tracer.start_as_current_span(
                f"invoke_agent {agent_name}", attributes=agent_span_attributes
            ) as agent_span:
                agent_span.set_attribute("gen_ai.conversation.id", session_id)
                agent_span.set_attribute(
                    "gen_ai.system_instructions",
                    json.dumps([{"type": "text", "content": agent.instruction}]),
                )
                agent_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt}]}]),
                )
                usage_metadata = None
                finish_reason = None
                last_text = ""
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
                ):
                    if getattr(event, "usage_metadata", None) is not None:
                        usage_metadata = event.usage_metadata
                    if getattr(event, "finish_reason", None) is not None:
                        finish_reason = getattr(event.finish_reason, "value", event.finish_reason)
                    if event.content and event.content.parts and event.content.parts[0].text:
                        last_text = event.content.parts[0].text
                if usage_metadata is not None:
                    if getattr(usage_metadata, "prompt_token_count", None) is not None:
                        agent_span.set_attribute("gen_ai.usage.input_tokens", usage_metadata.prompt_token_count)
                    if getattr(usage_metadata, "candidates_token_count", None) is not None:
                        agent_span.set_attribute("gen_ai.usage.output_tokens", usage_metadata.candidates_token_count)
                if finish_reason is not None:
                    agent_span.set_attribute("gen_ai.response.finish_reasons", [str(finish_reason).lower()])
                if last_text:
                    agent_span.set_attribute(
                        "gen_ai.output.messages",
                        json.dumps(
                            [
                                {
                                    "role": "assistant",
                                    "parts": [{"type": "text", "content": last_text}],
                                    "finish_reason": str(finish_reason or "stop").lower(),
                                }
                            ]
                        ),
                    )
                after = await session_service.get_session(app_name="test_app", user_id=user_id, session_id=session_id)
                # The context this invocation ran with, as ADK recorded it: every
                # skill loaded in the session up to here, including any this
                # invocation loaded, and whether a compaction has replaced its
                # instructions with a summary. Read once the invocation is over so a
                # skill it loaded itself is in the set, and set before the span ends.
                skills_in_context = _skills_in_context(after.events)
                if skills_in_context:
                    agent_span.set_attribute("gen_ai.skills", json.dumps(skills_in_context))
            # Skills this invocation activated
            activated = [name for name, _ in _resolved_skill_loads(after.events[events_before:])]
            _invoke_agent_skill_loads.record(len(activated), {"gen_ai.agent.name": agent_name})

        async def invoke_graph(session_id, prompt):
            """One workflow invocation, wrapped in its `invoke_workflow` span.

            One `runner.run_async` over a `Workflow` runs every node of the
            graph, so the call coordinates both agents rather than being a
            standalone agent run — the boundary the workflow span is for.
            """
            before = await session_service.get_session(app_name="test_app", user_id=user_id, session_id=session_id)
            events_before = len(before.events)
            with _reference_tracer.start_as_current_span(
                f"invoke_workflow {workflow.name}",
                attributes={"gen_ai.operation.name": "invoke_workflow"},
            ) as workflow_span:
                workflow_span.set_attribute("gen_ai.workflow.name", workflow.name)
                workflow_span.set_attribute("gen_ai.conversation.id", session_id)
                workflow_span.set_attribute(
                    "gen_ai.input.messages",
                    json.dumps([{"role": "user", "parts": [{"type": "text", "content": prompt}]}]),
                )
                finish_reason = None
                last_text = ""
                async for event in workflow_runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
                ):
                    if getattr(event, "finish_reason", None) is not None:
                        finish_reason = getattr(event.finish_reason, "value", event.finish_reason)
                    if event.content and event.content.parts and event.content.parts[0].text:
                        last_text = event.content.parts[0].text
                if last_text:
                    workflow_span.set_attribute(
                        "gen_ai.output.messages",
                        json.dumps(
                            [
                                {
                                    "role": "assistant",
                                    "parts": [{"type": "text", "content": last_text}],
                                    "finish_reason": str(finish_reason or "stop").lower(),
                                }
                            ]
                        ),
                    )
            after = await session_service.get_session(app_name="test_app", user_id=user_id, session_id=session_id)
            # Skills the workflow activated
            activated = [name for name, _ in _resolved_skill_loads(after.events[events_before:])]
            _invoke_workflow_skill_loads.record(len(activated), {"gen_ai.workflow.name": workflow.name})

        async def _phases():
            # Phase 1, the skill lifecycle. Each stage is its own conversation, so
            # each turn is a first turn and the model reaches for the stage's tool.
            lifecycle_runner = build_runner()
            stages = [
                ("What can you help me with?", "list_skills"),
                ("Review the pending change.", "load_skill"),
                ("What does the review policy require?", "load_skill_resource"),
                ("Run the bundled checks.", "run_skill_script"),
            ]
            for prompt, tool_name in stages:
                session = await session_service.create_session(app_name="test_app", user_id=user_id)
                await invoke(lifecycle_runner, session.id, prompt, tool_name)

            # A model can also name a skill that does not exist. No skill resolves,
            # so the span carries the name the call asked for and the failure, and
            # nothing else about a skill. The load is still counted.
            load_skill_tool.skill_names = ["ocr-tables"]
            session = await session_service.create_session(app_name="test_app", user_id=user_id)
            await invoke(lifecycle_runner, session.id, "Extract the tables from this PDF.", "load_skill")

            # A script the skill does not bundle fails before anything runs, so the
            # execution carries `error.type` and no exit code — the two describe
            # different outcomes and neither substitutes for the other.
            run_script_tool.script_paths = ["scripts/lint.sh"]
            run_script_tool.commands = [f"bash {toolset.skills_folder / 'code-review' / 'scripts/lint.sh'}"]
            session = await session_service.create_session(app_name="test_app", user_id=user_id)
            await invoke(lifecycle_runner, session.id, "Lint it too.", "run_skill_script")

            # Phase 2, compaction. One long conversation with compaction configured
            # every third invocation: the skill loaded first falls inside a
            # compacted range while the one loaded after it is still held in full,
            # so the last invocation sees both states at once.
            compacting_runner = build_runner(compaction_interval=3)
            session = await session_service.create_session(app_name="test_app", user_id=user_id)
            load_skill_tool.skill_names = ["code-review"]
            await invoke(compacting_runner, session.id, "Review the pending change.", "load_skill")
            await invoke(compacting_runner, session.id, "Summarize the first finding.")
            await invoke(compacting_runner, session.id, "And the second one?")
            load_skill_tool.skill_names = ["pdf-processing"]
            await invoke(compacting_runner, session.id, "Now read the attached PDF.", "load_skill")
            await invoke(compacting_runner, session.id, "What did both of those tell you?")

            # Phase 3, a workflow. Its two agents each load their own skill, so
            # the workflow-scoped count spans loads made by more than one agent
            # while each agent-scoped count sees only its own.
            session = await session_service.create_session(app_name="test_app", user_id=user_id)
            await invoke_graph(session.id, "Review the pending change and report on it.")

        async def _run():
            try:
                await _phases()
            finally:
                # Releases the environment the scripts ran in. `close()` removes
                # only a workspace it created itself, so the explicit one above is
                # the scenario's to remove.
                await toolset.close()
                await reviewer_toolset.close()
                await reporter_toolset.close()

        try:
            asyncio.run(_run())
        finally:
            shutil.rmtree(working_dir, ignore_errors=True)


def main():
    print("=== Reference Implementation: Google ADK Reference Implementation ===")

    tp, lp, mp = setup_otel()

    span_counter = SpanCounter()
    tp.add_span_processor(span_counter)

    run_agent_reference()
    run_memory_reference()
    run_skills_reference()

    print(f"\n  [diagnostic] Spans generated: {span_counter.count}")

    time.sleep(2)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
