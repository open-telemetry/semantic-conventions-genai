"""Native telemetry scenario for Microsoft Agent Framework."""

import asyncio
import os
import pathlib
import subprocess
import sys
from typing import Annotated

from opentelemetry import trace
from reference_shared import flush_and_shutdown, reference_meter, setup_otel

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"] + "/v1"
SKILLS_DIR = pathlib.Path(__file__).parent / "skills"
# What the skill under SKILLS_DIR actually holds, keyed by the tool that takes it.
SKILL_TOOL_ENUMS = {
    "load_skill": {"skill_name": ["code-review"]},
    "read_skill_resource": {
        "skill_name": ["code-review"],
        "resource_name": ["references/review_policy.md"],
    },
    "run_skill_script": {
        "skill_name": ["code-review"],
        "script_name": ["scripts/run_checks.py"],
    },
}

_reference_meter = reference_meter()

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
_skill_script_executions = _reference_meter.create_counter(
    "gen_ai.skill.script.executions",
    unit="{execution}",
    description="The number of times a skill's script was executed.",
)


async def run_agent_tool_call():
    """Scenario: Agent Framework agent execution with native telemetry."""
    from agent_framework import Agent, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatClient

    print("  [agent_run] agent with tool calling (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    client = OpenAIChatClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    agent = Agent(
        client=client,
        id="weather-agent",
        name="WeatherAgent",
        description="Answers weather questions with a function tool.",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    result = await agent.run(
        "What's the weather in Seattle?",
        options={
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 64,
        },
    )
    print(f"    -> {result.text[:60]}")


async def run_tool_call():
    """Scenario: Agent Framework chat client tool calling with native telemetry."""
    from agent_framework import Message, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatCompletionClient

    print("  [chat_tool_call] chat client with tool calling (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    response = await client.get_response(
        [Message(role="user", contents=["What's the weather in Seattle?"])],
        options={
            "tools": [get_weather],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 64,
            "seed": 7,
            "stop": ["<END>"],
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        },
    )
    print(f"    -> {response.text[:60]}")


async def run_chat_completion_agent_tool_call():
    """Scenario: Agent Framework agent execution through Chat Completions."""
    from agent_framework import Agent, tool
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatCompletionClient

    print("  [agent_chat_completion] agent with Chat Completions (native telemetry)")

    enable_sensitive_telemetry(force=True)

    @tool(approval_mode="never_require")
    def get_weather(
        location: Annotated[str, "The location to get the weather for."],
    ) -> str:
        """Get the weather for a given location."""
        return f"Sunny in {location}"

    client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    agent = Agent(
        client=client,
        id="weather-agent-chat-completions",
        name="WeatherAgentChatCompletions",
        description="Answers weather questions with a function tool.",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    result = await agent.run(
        "What's the weather in Seattle?",
        options={
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 64,
            "seed": 7,
            "stop": ["<END>"],
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        },
    )
    print(f"    -> {result.text[:60]}")


async def run_agent_workflow():
    """Scenario: Agent Framework workflow execution with native telemetry."""
    from agent_framework import Agent, WorkflowBuilder
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatClient

    print("  [workflow] two-agent workflow (native telemetry)")

    enable_sensitive_telemetry(force=True)

    client = OpenAIChatClient(
        model="gpt-4o-mini",
        base_url=MOCK_BASE_URL,
        api_key="mock-key",
    )
    writer_agent = Agent(
        client=client,
        name="writer",
        instructions="You are a concise copy writer.",
    )
    reviewer_agent = Agent(
        client=client,
        name="reviewer",
        instructions="You review slogans and suggest one short improvement.",
    )
    workflow = (
        WorkflowBuilder(
            start_executor=writer_agent,
            name="slogan_review_workflow",
            description="Drafts and reviews a short slogan.",
            output_from=[reviewer_agent],
        )
        .add_edge(writer_agent, reviewer_agent)
        .build()
    )

    result = await workflow.run("Create a slogan for a compact electric van.")
    outputs = result.get_outputs()
    if outputs:
        print(f"    -> {str(outputs[0])[:60]}")


async def run_skills():
    """Scenario: Agent Skills through Agent Framework's `SkillsProvider`.

    The provider exposes the [Agent Skills](https://agentskills.io) lifecycle to
    the model as three tools — `load_skill`, `read_skill_resource` and
    `run_skill_script` — so the framework's own tool loop runs each stage and
    its native `execute_tool` span is where the skill attributes belong. The
    reference stamps them onto that span from inside the tool call, the same way
    a framework's own instrumentation would.
    """
    from agent_framework import Agent, SkillsProvider
    from agent_framework.observability import enable_sensitive_telemetry
    from agent_framework.openai import OpenAIChatClient

    print("  [skills] SkillsProvider skill lifecycle (reference implementation)")

    enable_sensitive_telemetry(force=True)
    activated: list[str] = []

    def run_script(skill, script, args=None):
        """Application-supplied runner for file-based skill scripts.

        Agent Framework hands file-based script execution to the caller and takes
        back whatever it returns, so the process outcome — an exit code — is the
        application's to define and is not in the framework's contract.
        `gen_ai.skill.script.exit_code` is therefore not capturable here.
        """
        completed = subprocess.run(
            [sys.executable, str(pathlib.Path(skill.path) / script.name)],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout.strip()

    class _InstrumentedSkillsProvider(SkillsProvider):
        """Adds `gen_ai.skill.*` to the framework's own `execute_tool` span.

        Overriding `_create_tools` is the provider's own extension point for the
        tool set it hands the model. `stage_tool` narrows that set to one tool
        per run: the mock model server calls the first tool it is offered, so
        this is what makes the model's choice deterministic.
        """

        stage_tool: str | None = None

        def _create_tools(self, skills):
            def instrument(tool_name, func):
                async def wrapper(**kwargs):
                    span = trace.get_current_span()
                    # `direct`: the model's call names the skill it operates on.
                    skill_name = kwargs.get("skill_name")
                    if skill_name:
                        span.set_attribute("gen_ai.skill.name", skill_name)
                    # `direct`: the provider resolved the skills for this run, so
                    # each one's frontmatter and the folder it was read from are
                    # in hand before the call runs.
                    skill = self._find_skill(skills, skill_name) if isinstance(skill_name, str) else None
                    if skill is not None:
                        span.set_attribute("gen_ai.skill.description", skill.frontmatter.description)
                        span.set_attribute("gen_ai.skill.source.uri", pathlib.Path(skill.path).as_uri())
                    if tool_name == SkillsProvider.READ_SKILL_RESOURCE_TOOL_NAME:
                        # `direct`: the resource path is a call argument, and the
                        # provider names resources by their path within the skill.
                        span.set_attribute("gen_ai.skill.resource.path", kwargs["resource_name"])
                    if tool_name == SkillsProvider.RUN_SKILL_SCRIPT_TOOL_NAME:
                        # `direct`: the script path is a call argument.
                        span.set_attribute("gen_ai.skill.script.path", kwargs["script_name"])
                    result = await func(**kwargs)
                    # The span carries the name the call asked for either way; the
                    # metrics take it only once the provider has resolved it to a
                    # skill, so a name the model invented cannot enter the dimension.
                    attributes = {"gen_ai.agent.name": "SkillAgent"}
                    if skill is not None:
                        attributes["gen_ai.skill.name"] = skill_name
                    if tool_name == SkillsProvider.LOAD_SKILL_TOOL_NAME:
                        if skill is not None:
                            activated.append(skill_name)
                        _skill_loads.add(1, attributes)
                    if tool_name == SkillsProvider.RUN_SKILL_SCRIPT_TOOL_NAME:
                        if skill is not None and skill.get_script(kwargs["script_name"]) is not None:
                            attributes["gen_ai.skill.script.path"] = kwargs["script_name"]
                        _skill_script_executions.add(1, attributes)
                    return result

                return wrapper

            tools = []
            for base in super()._create_tools(skills):
                if self.stage_tool is not None and base.name != self.stage_tool:
                    continue
                # Narrow the declared parameters to the values that exist. A
                # deployment does this to stop a model inventing names, and it is
                # what lets the mock model server choose a resolvable one. Only
                # the declaration changes; the handler stays the provider's own.
                properties = base.parameters()["properties"]
                for parameter, values in SKILL_TOOL_ENUMS[base.name].items():
                    properties[parameter]["enum"] = values
                base.func = instrument(base.name, base.func)
                tools.append(base)
            return tools

    provider = _InstrumentedSkillsProvider.from_paths(
        str(SKILLS_DIR),
        script_runner=run_script,
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
        disable_run_skill_script_approval=True,
    )

    # Each stage is its own run: the mock model server offers a tool call only
    # while the conversation carries no tool result yet.
    stages = [
        ("Review the pending change.", SkillsProvider.LOAD_SKILL_TOOL_NAME),
        ("What does the review policy require?", SkillsProvider.READ_SKILL_RESOURCE_TOOL_NAME),
        ("Run the bundled checks.", SkillsProvider.RUN_SKILL_SCRIPT_TOOL_NAME),
    ]
    for prompt, stage_tool in stages:
        provider.stage_tool = stage_tool
        activated.clear()
        async with Agent(
            client=OpenAIChatClient(model="gpt-4o-mini", base_url=MOCK_BASE_URL, api_key="mock-key"),
            id="skill-agent",
            name="SkillAgent",
            description="Reviews code changes with Agent Skills.",
            instructions="You review code changes.",
            context_providers=[provider],
        ) as agent:
            result = await agent.run(prompt)
            print(f"    -> {result.text[:60]}")
        # Skills this invocation activated
        _invoke_agent_skill_loads.record(len(activated), {"gen_ai.agent.name": "SkillAgent"})


def main():
    print("=== Native Telemetry: Microsoft Agent Framework ===")

    tp, lp, mp = setup_otel()

    asyncio.run(run_agent_tool_call())
    asyncio.run(run_tool_call())
    asyncio.run(run_chat_completion_agent_tool_call())
    asyncio.run(run_agent_workflow())
    asyncio.run(run_skills())

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
