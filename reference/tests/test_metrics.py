"""Verify the committed data files survive into the reports.

How a run is reduced into ``data.json`` is the conformance runner's business
and is tested there; what is left here is this repo's own view of it -- the
specs the reports are built from, and the mapping from the registry names a
data file uses onto the shorter keys the reports address signals by.

Runnable directly (``python tests/test_metrics.py``) or under pytest.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from semconv_genai.data_files import _normalize_scenario_data_entry, load_scenario_data_files
from semconv_genai.semconv_model import entity_specs, metric_specs, span_specs

_TOOL_CALLS = "gen_ai.invoke_agent.tool_calls"
_INFERENCE_CALLS = "gen_ai.invoke_agent.inference_calls"
_SEMCONV_ROOT = Path(__file__).resolve().parents[2]
_FOUNDRY_PROJECT_ID = (
    "/subscriptions/b17253fa-f327-42d6-9686-f3e553e24763/resourceGroups/hanchi-test/"
    "providers/Microsoft.CognitiveServices/accounts/hancwang-swectr/projects/hancwang-swectr-proj"
)
_FOUNDRY_CONNECTION_ID = f"{_FOUNDRY_PROJECT_ID}/connections/reference-connection"


def _load_semconv_yaml(relative_path: str) -> dict:
    return yaml.safe_load((_SEMCONV_ROOT / relative_path).read_text(encoding="utf-8"))


def _required_level(attribute: dict) -> tuple[str, str | None]:
    level = attribute["requirement_level"]
    if isinstance(level, str):
        return level, None
    name, condition = next(iter(level.items()))
    return name, condition


def _attribute_path(node: ast.AST) -> tuple[str, ...]:
    path = []
    while isinstance(node, ast.Attribute):
        path.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        path.append(node.id)
    return tuple(reversed(path))


def _load_foundry_run_invoke_agent(*, default_http_client_factory=SimpleNamespace):
    scenario_path = _SEMCONV_ROOT / "reference" / "scenarios" / "azure-ai-foundry" / "scenario.py"
    tree = ast.parse(scenario_path.read_text(encoding="utf-8"))
    run_invoke_agent = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_invoke_agent"
    )
    spans = {}

    class FakeSpan:
        def __init__(self, name, attributes=None):
            self.name = name
            self.attributes = dict(attributes or {})
            self.exception = None
            self.status = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_value is not None:
                self.exception = exc_value
                if self.status is None:
                    self.status = ("error", f"{exc_type.__name__}: {exc_value}")
            return False

        def set_attribute(self, name, value):
            self.attributes[name] = value

        def set_status(self, code, description):
            self.status = (code, description)

    class FakeTracer:
        def start_as_current_span(self, name, **kwargs):
            span = FakeSpan(name, kwargs.get("attributes"))
            spans[name] = span
            return span

    namespace = {
        "AGENT_DESCRIPTION": "description",
        "AGENT_INSTRUCTIONS": "instructions",
        "AGENT_MODEL": "model",
        "AGENT_NAME": "refimpl-test-agent",
        "DefaultHttpxClient": default_http_client_factory,
        "PromptAgentDefinition": SimpleNamespace,
        "SpanKind": SimpleNamespace(CLIENT="client"),
        "StatusCode": SimpleNamespace(ERROR="error"),
        "USER_INPUT": "Hello, agent!",
        "_SERVER_ADDRESS": "foundry-resource.services.ai.azure.com",
        "_SERVER_PORT": None,
        "_route_agent_request_to_mock": object(),
        "json": json,
        "tracer": FakeTracer(),
    }
    module = ast.Module(body=[run_invoke_agent], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(scenario_path), "exec"), namespace)
    run_invoke_agent = namespace["run_invoke_agent"]

    def invoke(client, connection=None):
        if connection is None:
            connection = SimpleNamespace(id=_FOUNDRY_CONNECTION_ID)
        return run_invoke_agent(client, connection)

    return invoke, spans


def _run_foundry_program(
    client,
    run_invoke_agent,
    flush_and_shutdown,
    *,
    project_client_factory=None,
):
    scenario_path = _SEMCONV_ROOT / "reference" / "scenarios" / "azure-ai-foundry" / "scenario.py"
    tree = ast.parse(scenario_path.read_text(encoding="utf-8"))
    main_guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )
    if client is not None:
        client.connections = SimpleNamespace(list=lambda: [SimpleNamespace(id=_FOUNDRY_CONNECTION_ID)])

    namespace = {
        "AIProjectClient": project_client_factory or (lambda **kwargs: client),
        "FOUNDRY_PROJECT_ENDPOINT": "https://foundry-resource.services.ai.azure.com/api/projects/reference-project",
        "MockCredential": lambda: object(),
        "MockTransportPolicy": lambda: object(),
        "SansIOHTTPPolicy": lambda: object(),
        "flush_and_shutdown": flush_and_shutdown,
        "run_invoke_agent": lambda actual_client, connection: run_invoke_agent(actual_client),
        "setup_otel": lambda: ("tracer-provider", "logger-provider", "meter-provider"),
    }
    module = ast.Module(body=main_guard.body, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(scenario_path), "exec"), namespace)


def test_metric_specs_expose_recommended_agent_name():
    specs = metric_specs()
    assert specs, "expected at least one tracked metric"
    # Only the per-invocation agent metrics are agent-scoped; gen_ai.client.*
    # metrics (token usage, operation duration) are not dimensioned by
    # gen_ai.agent.name, so this checks the invoke_agent metrics specifically
    # rather than every tracked metric.
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert "gen_ai.agent.name" in specs[name].recommended, name


def test_metric_specs_are_named_as_the_registry_names_them():
    for name, spec in metric_specs().items():
        assert spec.registry_id == name, name


def test_committed_google_adk_metrics_round_trip():
    entries = {e.library: e for e in load_scenario_data_files()}
    adk = entries["google-adk"]
    for name in (_INFERENCE_CALLS, _TOOL_CALLS):
        assert adk.metrics[name]["gen_ai.agent.name"] == "present", name


def test_inference_scenarios_report_inference_duration():
    entries = {entry.library: entry for entry in load_scenario_data_files()}
    for library in ("agent-framework", "anthropic", "groq"):
        metrics = entries[library].metrics
        assert "gen_ai.client.inference.duration" in metrics, library
        assert "gen_ai.client.operation.duration" not in metrics, library
        assert metrics["gen_ai.client.inference.duration"]["gen_ai.operation.name"] == "present", library
        assert metrics["gen_ai.client.inference.duration"]["gen_ai.provider.name"] == "present", library


def test_entity_specs_expose_required_id():
    specs = entity_specs()
    assert "gen_ai.main_agent" in specs
    assert "gen_ai.main_agent.id" in specs["gen_ai.main_agent"].required


def test_entities_keep_their_registry_names():
    entry = _normalize_scenario_data_entry(
        {"entities": {"gen_ai.main_agent": ["gen_ai.main_agent.id"]}},
        "fake",
    )
    assert entry.entities["gen_ai.main_agent"]["gen_ai.main_agent.id"] == "present"


def test_entities_with_sections_round_trip():
    entry = _normalize_scenario_data_entry(
        {
            "entities": {
                "gen_ai.main_agent": {
                    "identity": ["gen_ai.main_agent.id"],
                    "description": ["gen_ai.main_agent.description", "gen_ai.main_agent.name"],
                }
            }
        },
        "fake",
    )
    assert entry.entities["gen_ai.main_agent"]["gen_ai.main_agent.id"] == "present"
    assert entry.entities["gen_ai.main_agent"]["gen_ai.main_agent.description"] == "present"
    assert entry.entities["gen_ai.main_agent"]["gen_ai.main_agent.name"] == "present"


def test_registry_span_names_map_onto_report_keys():
    """A data file names spans as the registry does; reports use short keys."""
    entry = _normalize_scenario_data_entry(
        {"spans": {"gen_ai.client.inference": ["gen_ai.operation.name"]}},
        "fake",
    )
    assert set(entry.spans) == {"inference"}
    assert entry.spans["inference"]["gen_ai.operation.name"] == "present"
    # Everything else the span type declares is reported as absent, not missing.
    assert entry.spans["inference"]["gen_ai.provider.name"] == "absent"


def test_events_keep_their_registry_names():
    entry = _normalize_scenario_data_entry(
        {"events": {"gen_ai.evaluation.result": ["gen_ai.evaluation.name"]}},
        "fake",
    )
    assert entry.events["gen_ai.evaluation.result"]["gen_ai.evaluation.name"] == "present"


def test_span_types_absent_from_a_data_file_are_not_reported():
    entry = _normalize_scenario_data_entry({"spans": {}}, "fake")
    assert entry.spans == {}


def test_span_specs_are_named_as_the_registry_names_them():
    for key, spec in span_specs().items():
        assert spec.registry_id.startswith("gen_ai."), key


def test_foundry_invoke_agent_refinement_contract():
    registry = _load_semconv_yaml("model/gen-ai/registry.yaml")
    provider = next(
        member
        for attribute in registry["attributes"]
        if attribute["key"] == "gen_ai.provider.name"
        for member in attribute["type"]["members"]
        if member["id"] == "microsoft.foundry"
    )
    assert provider["value"] == "microsoft.foundry"
    provider_doc = "https://learn.microsoft.com/azure/foundry/agents/overview"
    assert provider["brief"] == f"[Microsoft Foundry Agent Service]({provider_doc})"

    foundry_registry = _load_semconv_yaml("model/microsoft/foundry/registry.yaml")
    project_id = next(
        attribute for attribute in foundry_registry["attributes"] if attribute["key"] == "microsoft.foundry.project.id"
    )
    assert project_id["type"] == "string"
    assert project_id["brief"] == "The full Azure Resource Manager resource ID of the Microsoft Foundry project.\n"
    assert project_id["examples"] == [_FOUNDRY_PROJECT_ID]

    spans = _load_semconv_yaml("model/gen-ai/spans.yaml")
    refinement = next(
        item for item in spans["span_refinements"] if item["id"] == "microsoft.foundry.gen_ai.invoke_agent.client"
    )
    assert refinement["ref"] == "gen_ai.invoke_agent.client"
    assert refinement["brief"] == (
        f"Semantic Conventions for [Microsoft Foundry Agent Service]({provider_doc}) client spans extend and "
        "override the semantic conventions for [Gen AI Spans](gen-ai-spans.md).\n"
    )
    assert refinement["note"] == (
        "This refinement applies when invoking a remotely hosted Foundry agent through the "
        "agent-scoped OpenAI Responses API.\n\n"
        '`gen_ai.provider.name` MUST be set to `"microsoft.foundry"` and SHOULD be provided '
        "**at span creation time**.\n"
    )

    assert {attribute["ref"] for attribute in refinement["attributes"]} == {
        "gen_ai.agent.name",
        "gen_ai.conversation.id",
        "gen_ai.request.model",
        "microsoft.foundry.project.id",
        "server.port",
    }
    attributes = {attribute["ref"]: attribute for attribute in refinement["attributes"]}

    assert _required_level(attributes["gen_ai.agent.name"]) == ("required", None)
    assert _required_level(attributes["gen_ai.conversation.id"]) == (
        "conditionally_required",
        "When the request references a Foundry conversation.",
    )
    assert _required_level(attributes["gen_ai.request.model"]) == (
        "recommended",
        "When the invoked agent has one configured model and it is readily available to instrumentation.",
    )
    assert _required_level(attributes["microsoft.foundry.project.id"]) == (
        "conditionally_required",
        "When the full project resource ID is readily available to instrumentation.",
    )
    assert _required_level(attributes["server.port"]) == (
        "conditionally_required",
        "When the endpoint port is not the default port 443.",
    )


def test_foundry_agent_reference_uses_agent_scoped_responses_client():
    scenario_path = _SEMCONV_ROOT / "reference" / "scenarios" / "azure-ai-foundry" / "scenario.py"
    tree = ast.parse(scenario_path.read_text(encoding="utf-8"))

    assignments = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    agent_call = assignments["agent"]
    assert isinstance(agent_call, ast.Call)
    assert _attribute_path(agent_call.func) == ("client", "agents", "create_version")

    openai_client_call = assignments["openai_client"]
    assert isinstance(openai_client_call, ast.Call)
    assert _attribute_path(openai_client_call.func) == ("client", "get_openai_client")
    openai_client_arguments = {keyword.arg: keyword.value for keyword in openai_client_call.keywords}
    assert ast.unparse(openai_client_arguments["agent_name"]) == "agent.name"

    conversation_call = assignments["conversation"]
    assert isinstance(conversation_call, ast.Call)
    assert _attribute_path(conversation_call.func) == ("openai_client", "conversations", "create")

    response_call = assignments["response"]
    assert isinstance(response_call, ast.Call)
    assert _attribute_path(response_call.func) == ("openai_client", "responses", "create")
    response_arguments = {keyword.arg: keyword.value for keyword in response_call.keywords}
    assert set(response_arguments) == {"conversation", "input"}
    assert ast.unparse(response_arguments["conversation"]) == "conversation.id"
    assert ast.unparse(response_arguments["input"]) == "USER_INPUT"

    project_id = assignments["project_id"]
    assert isinstance(project_id, ast.Subscript)
    assert ast.unparse(project_id) == "connection.id.rsplit('/connections/', 1)[0]"

    invoke_attributes = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant)
            and key.value == "gen_ai.operation.name"
            and isinstance(value, ast.Constant)
            and value.value == "invoke_agent"
            for key, value in zip(node.keys, node.values, strict=True)
        )
    )
    invoke_attribute_values = {
        key.value: value
        for key, value in zip(invoke_attributes.keys, invoke_attributes.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert ast.literal_eval(invoke_attribute_values["gen_ai.provider.name"]) == "microsoft.foundry"
    assert ast.unparse(invoke_attribute_values["gen_ai.agent.name"]) == "agent.name"
    assert ast.unparse(invoke_attribute_values["gen_ai.conversation.id"]) == "conversation.id"
    assert ast.unparse(invoke_attribute_values["microsoft.foundry.project.id"]) == "project_id"
    assert not any(isinstance(node, ast.Constant) and node.value == "agent_reference" for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Constant) and node.value == "gen_ai.response.finish_reasons" for node in ast.walk(tree)
    )
    assert not any(isinstance(node, ast.Constant) and node.value == "gen_ai.output.type" for node in ast.walk(tree))


def test_foundry_agent_reference_records_project_id_from_connection():
    run_invoke_agent, spans = _load_foundry_run_invoke_agent()
    create_version_arguments = {}

    class FakeAgents:
        def create_version(self, **kwargs):
            create_version_arguments.update(kwargs)
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            pass

    class FakeConversations:
        def create(self):
            return SimpleNamespace(id="conversation-id")

        def delete(self, **kwargs):
            pass

    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(id="response-id", output_text="", usage=None)

    class FakeOpenAIClient:
        conversations = FakeConversations()
        responses = FakeResponses()

        def close(self):
            pass

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            return FakeOpenAIClient()

    run_invoke_agent(FakeClient(), SimpleNamespace(id=_FOUNDRY_CONNECTION_ID))

    invoke_span = spans["invoke_agent refimpl-test-agent"]
    assert invoke_span.attributes["microsoft.foundry.project.id"] == _FOUNDRY_PROJECT_ID
    search_tool = create_version_arguments["definition"].tools[1]
    assert search_tool["azure_ai_search"]["indexes"][0]["project_connection_id"] == _FOUNDRY_CONNECTION_ID


def test_foundry_agent_reference_records_create_agent_error_type():
    run_invoke_agent, spans = _load_foundry_run_invoke_agent()
    creation_error = RuntimeError("agent creation failed")

    class FakeAgents:
        def create_version(self, **kwargs):
            raise creation_error

    class FakeClient:
        agents = FakeAgents()

    with pytest.raises(RuntimeError) as caught:
        run_invoke_agent(FakeClient())

    assert caught.value is creation_error
    create_span = spans["create_agent refimpl-test-agent"]
    assert create_span.attributes["error.type"] == "RuntimeError"
    assert create_span.status == ("error", "RuntimeError: agent creation failed")
    assert create_span.exception is creation_error


def test_foundry_agent_reference_closes_owned_http_client_when_openai_client_construction_fails():
    events = []
    construction_error = RuntimeError("OpenAI client construction failed")

    class FakeHttpClient:
        def __init__(self, **kwargs):
            events.append("http_client.create")

        def close(self):
            events.append("http_client.close")

    class FakeAgents:
        def create_version(self, **kwargs):
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            events.append("agents.delete_version")

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            assert isinstance(kwargs["http_client"], FakeHttpClient)
            events.append("get_openai_client")
            raise construction_error

    run_invoke_agent, _ = _load_foundry_run_invoke_agent(default_http_client_factory=FakeHttpClient)

    with pytest.raises(RuntimeError) as caught:
        run_invoke_agent(FakeClient())

    assert caught.value is construction_error
    assert events == [
        "http_client.create",
        "get_openai_client",
        "http_client.close",
        "agents.delete_version",
    ]


def test_foundry_agent_reference_groups_owned_http_client_cleanup_failure_after_construction_error():
    events = []
    construction_error = RuntimeError("OpenAI client construction failed")
    http_client_cleanup_error = RuntimeError("HTTP client cleanup failed")
    agent_cleanup_error = RuntimeError("agent cleanup failed")

    class FakeHttpClient:
        def __init__(self, **kwargs):
            events.append("http_client.create")

        def close(self):
            events.append("http_client.close")
            raise http_client_cleanup_error

    class FakeAgents:
        def create_version(self, **kwargs):
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            events.append("agents.delete_version")
            raise agent_cleanup_error

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            assert isinstance(kwargs["http_client"], FakeHttpClient)
            events.append("get_openai_client")
            raise construction_error

    run_invoke_agent, _ = _load_foundry_run_invoke_agent(default_http_client_factory=FakeHttpClient)

    with pytest.raises(BaseExceptionGroup) as caught:
        run_invoke_agent(FakeClient())

    assert caught.value.exceptions == (
        construction_error,
        http_client_cleanup_error,
        agent_cleanup_error,
    )
    assert events == [
        "http_client.create",
        "get_openai_client",
        "http_client.close",
        "agents.delete_version",
    ]


def test_foundry_agent_reference_preserves_invocation_failure_when_cleanup_fails():
    run_invoke_agent, spans = _load_foundry_run_invoke_agent()
    invocation_error = RuntimeError("invocation failed")
    conversation_cleanup_error = RuntimeError("conversation cleanup failed")
    agent_cleanup_error = RuntimeError("agent cleanup failed")

    class FakeResponses:
        def create(self, **kwargs):
            raise invocation_error

    class FakeConversations:
        def create(self):
            return SimpleNamespace(id="conversation-id")

        def delete(self, **kwargs):
            raise conversation_cleanup_error

    class FakeOpenAIClient:
        conversations = FakeConversations()
        responses = FakeResponses()

        def close(self):
            pass

    class FakeAgents:
        def create_version(self, **kwargs):
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            raise agent_cleanup_error

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            return FakeOpenAIClient()

    with pytest.raises(ExceptionGroup) as caught:
        run_invoke_agent(FakeClient())

    raised_error = caught.value
    assert raised_error.exceptions == (
        invocation_error,
        conversation_cleanup_error,
        agent_cleanup_error,
    )
    invoke_span = spans["invoke_agent refimpl-test-agent"]
    assert invoke_span.attributes["error.type"] == "RuntimeError"
    assert invoke_span.status == ("error", "invocation failed")
    assert invoke_span.exception is invocation_error


def test_foundry_agent_reference_attempts_all_cleanup_after_base_exceptions():
    run_invoke_agent, _ = _load_foundry_run_invoke_agent()
    events = []
    invocation_error = KeyboardInterrupt("invocation interrupted")
    conversation_cleanup_error = SystemExit("conversation cleanup exited")
    client_cleanup_error = KeyboardInterrupt("OpenAI client close interrupted")
    agent_cleanup_error = SystemExit("agent cleanup exited")

    class FakeResponses:
        def create(self, **kwargs):
            events.append("responses.create")
            raise invocation_error

    class FakeConversations:
        def create(self):
            return SimpleNamespace(id="conversation-id")

        def delete(self, **kwargs):
            events.append("conversations.delete")
            raise conversation_cleanup_error

    class FakeOpenAIClient:
        conversations = FakeConversations()
        responses = FakeResponses()

        def close(self):
            events.append("openai_client.close")
            raise client_cleanup_error

    class FakeAgents:
        def create_version(self, **kwargs):
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            events.append("agents.delete_version")
            raise agent_cleanup_error

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            return FakeOpenAIClient()

    with pytest.raises(BaseExceptionGroup) as caught:
        run_invoke_agent(FakeClient())

    assert caught.value.exceptions == (
        invocation_error,
        conversation_cleanup_error,
        client_cleanup_error,
        agent_cleanup_error,
    )
    assert events == [
        "responses.create",
        "conversations.delete",
        "openai_client.close",
        "agents.delete_version",
    ]


def test_foundry_agent_reference_raises_cleanup_only_failure():
    run_invoke_agent, _ = _load_foundry_run_invoke_agent()
    cleanup_error = RuntimeError("conversation cleanup failed")

    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(id="response-id", output_text="", status="completed", usage=None)

    class FakeConversations:
        def create(self):
            return SimpleNamespace(id="conversation-id")

        def delete(self, **kwargs):
            raise cleanup_error

    class FakeOpenAIClient:
        conversations = FakeConversations()
        responses = FakeResponses()

        def close(self):
            pass

    class FakeAgents:
        def create_version(self, **kwargs):
            return SimpleNamespace(id="agent-id", name="refimpl-test-agent", version="1")

        def delete_version(self, **kwargs):
            pass

    class FakeClient:
        agents = FakeAgents()

        def get_openai_client(self, **kwargs):
            return FakeOpenAIClient()

    with pytest.raises(RuntimeError) as caught:
        run_invoke_agent(FakeClient())

    assert caught.value is cleanup_error


def test_foundry_program_preserves_run_failure_when_all_cleanup_fails():
    events = []
    run_error = RuntimeError("run failed")
    close_error = RuntimeError("project client close failed")
    shutdown_error = RuntimeError("telemetry shutdown failed")

    class FakeClient:
        def close(self):
            events.append("client.close")
            raise close_error

    client = FakeClient()

    def fail_run(actual_client):
        assert actual_client is client
        events.append("run_invoke_agent")
        raise run_error

    def fail_shutdown(tp, lp, mp):
        assert (tp, lp, mp) == ("tracer-provider", "logger-provider", "meter-provider")
        events.append("flush_and_shutdown")
        raise shutdown_error

    with pytest.raises(BaseExceptionGroup) as caught:
        _run_foundry_program(client, fail_run, fail_shutdown)

    assert caught.value.exceptions == (run_error, close_error, shutdown_error)
    assert events == ["run_invoke_agent", "client.close", "flush_and_shutdown"]


def test_foundry_program_attempts_shutdown_after_cleanup_only_base_exception():
    events = []
    close_error = KeyboardInterrupt("project client close interrupted")

    class FakeClient:
        def close(self):
            events.append("client.close")
            raise close_error

    client = FakeClient()

    def run_successfully(actual_client):
        assert actual_client is client
        events.append("run_invoke_agent")

    def shutdown_successfully(tp, lp, mp):
        assert (tp, lp, mp) == ("tracer-provider", "logger-provider", "meter-provider")
        events.append("flush_and_shutdown")

    with pytest.raises(KeyboardInterrupt) as caught:
        _run_foundry_program(client, run_successfully, shutdown_successfully)

    assert caught.value is close_error
    assert events == ["run_invoke_agent", "client.close", "flush_and_shutdown"]


def test_foundry_program_shuts_down_telemetry_when_client_construction_fails():
    events = []
    constructor_error = RuntimeError("project client construction failed")

    def fail_client_construction(**kwargs):
        events.append("AIProjectClient")
        raise constructor_error

    def fail_if_run(_client):
        pytest.fail("run_invoke_agent must not run without a project client")

    def shutdown_successfully(tp, lp, mp):
        assert (tp, lp, mp) == ("tracer-provider", "logger-provider", "meter-provider")
        events.append("flush_and_shutdown")

    with pytest.raises(RuntimeError) as caught:
        _run_foundry_program(
            None,
            fail_if_run,
            shutdown_successfully,
            project_client_factory=fail_client_construction,
        )

    assert caught.value is constructor_error
    assert events == ["AIProjectClient", "flush_and_shutdown"]


if __name__ == "__main__":
    test_metric_specs_expose_recommended_agent_name()
    test_metric_specs_are_named_as_the_registry_names_them()
    test_committed_google_adk_metrics_round_trip()
    test_inference_scenarios_report_inference_duration()
    test_entity_specs_expose_required_id()
    test_entities_keep_their_registry_names()
    test_entities_with_sections_round_trip()
    test_registry_span_names_map_onto_report_keys()
    test_events_keep_their_registry_names()
    test_span_types_absent_from_a_data_file_are_not_reported()
    test_span_specs_are_named_as_the_registry_names_them()
    test_foundry_invoke_agent_refinement_contract()
    test_foundry_agent_reference_uses_agent_scoped_responses_client()
    test_foundry_agent_reference_records_create_agent_error_type()
    test_foundry_agent_reference_closes_owned_http_client_when_openai_client_construction_fails()
    test_foundry_agent_reference_groups_owned_http_client_cleanup_failure_after_construction_error()
    test_foundry_agent_reference_preserves_invocation_failure_when_cleanup_fails()
    test_foundry_agent_reference_attempts_all_cleanup_after_base_exceptions()
    test_foundry_agent_reference_raises_cleanup_only_failure()
    test_foundry_program_preserves_run_failure_when_all_cleanup_fails()
    test_foundry_program_attempts_shutdown_after_cleanup_only_base_exception()
    test_foundry_program_shuts_down_telemetry_when_client_construction_fails()
    print("ok")
