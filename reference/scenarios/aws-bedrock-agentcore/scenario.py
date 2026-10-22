"""Reference implementation: AWS Bedrock AgentCore memory and evaluation APIs."""

import json
import os
from datetime import UTC, datetime

import boto3
from opentelemetry.trace import SpanKind
from reference_shared import (
    flush_and_shutdown,
    mock_server_host_port,
    reference_event_logger,
    reference_tracer,
    setup_otel,
)

MOCK_BASE_URL = os.environ["MOCK_LLM_URL"]

_reference_tracer = reference_tracer()

MEMORY_NAME = "customer-support-memory"
MEMORY_STRATEGY_ID = "strategy-user-preferences"
NAMESPACE = "/users/test-user/preferences"
CREATE_MEMORY_TEXT = "User prefers vegetarian meals."
UPDATED_MEMORY_TEXT = "User prefers vegetarian meals and dark mode."
QUERY_TEXT = "vegetarian meal preference"
TIMESTAMP = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
EVALUATOR_ID = "response_quality-mock01"
# One agent span from the session being evaluated, in the OTel JSON shape Evaluate accepts.
SESSION_SPAN = {
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "00f067aa0ba902b7",
    "name": "invoke_agent support-agent",
    "attributes": {"gen_ai.operation.name": "invoke_agent", "session.id": "session-001"},
}


def create_agentcore_control_client():
    """Create an AgentCore control client."""
    return boto3.client(
        "bedrock-agentcore-control",
        endpoint_url=MOCK_BASE_URL,
        region_name="us-east-1",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )


def create_agentcore_data_client():
    """Create an AgentCore data-plane client."""
    return boto3.client(
        "bedrock-agentcore",
        endpoint_url=MOCK_BASE_URL,
        region_name="us-east-1",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )


def run_create_memory_store_reference(client):
    """Scenario: Bedrock AgentCore create_memory_store operation."""
    print("  [create_memory_store] Bedrock AgentCore create_memory_store")
    event_expiry_duration = 30
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "create_memory_store",
        "gen_ai.provider.name": "aws.bedrock",
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "create_memory_store", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        response = client.create_memory(
            name=MEMORY_NAME,
            eventExpiryDuration=event_expiry_duration,
        )
        memory_id = response["memory"]["id"]
        span.set_attribute("gen_ai.memory.store.id", memory_id)
    return memory_id


def run_create_and_update_memory_reference(client, memory_id):
    """Scenario: AgentCore BatchCreateMemoryRecords and BatchUpdateMemoryRecords."""
    print("  [create_memory] Bedrock AgentCore BatchCreateMemoryRecords")
    create_records = [
        {
            "requestIdentifier": "create-record-1",
            "namespaces": [NAMESPACE],
            "content": {"text": CREATE_MEMORY_TEXT},
            "timestamp": TIMESTAMP,
            "memoryStrategyId": MEMORY_STRATEGY_ID,
            "metadata": {"author": {"stringValue": "user"}},
        }
    ]

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "create_memory",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.memory.store.id": memory_id,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "create_memory", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        response = client.batch_create_memory_records(
            memoryId=memory_id,
            records=create_records,
        )
        memory_record_id = response["successfulRecords"][0]["memoryRecordId"]
        span.set_attribute("gen_ai.memory.record.count", len(create_records))
        span.set_attribute(
            "gen_ai.memory.records",
            json.dumps(
                [
                    {
                        "content": create_records[0]["content"]["text"],
                        "id": memory_record_id,
                        "metadata": {"author": create_records[0]["metadata"]["author"]["stringValue"]},
                    }
                ]
            ),
        )

    print("  [update_memory] Bedrock AgentCore BatchUpdateMemoryRecords")
    update_records = [
        {
            "memoryRecordId": memory_record_id,
            "timestamp": TIMESTAMP,
            "content": {"text": UPDATED_MEMORY_TEXT},
            "namespaces": [NAMESPACE],
            "memoryStrategyId": MEMORY_STRATEGY_ID,
            "metadata": {"author": {"stringValue": "assistant"}},
        }
    ]

    span_attributes_2 = {
        "gen_ai.operation.name": "update_memory",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.memory.store.id": memory_id,
    }
    if host:
        span_attributes_2["server.address"] = host
    if port is not None:
        span_attributes_2["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "update_memory", kind=SpanKind.CLIENT, attributes=span_attributes_2
    ) as span:
        client.batch_update_memory_records(
            memoryId=memory_id,
            records=update_records,
        )
        span.set_attribute("gen_ai.memory.record.count", len(update_records))
        span.set_attribute(
            "gen_ai.memory.records",
            json.dumps(
                [
                    {
                        "content": update_records[0]["content"]["text"],
                        "id": update_records[0]["memoryRecordId"],
                        "metadata": {"author": update_records[0]["metadata"]["author"]["stringValue"]},
                    }
                ]
            ),
        )
    return memory_record_id


def run_search_memory_reference(client, memory_id):
    """Scenario: AgentCore RetrieveMemoryRecords."""
    print("  [search_memory] Bedrock AgentCore RetrieveMemoryRecords")
    search_criteria = {
        "searchQuery": QUERY_TEXT,
        "memoryStrategyId": MEMORY_STRATEGY_ID,
        "topK": 3,
    }

    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "search_memory",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.memory.store.id": memory_id,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "search_memory", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.memory.query.text", search_criteria["searchQuery"])
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespace=NAMESPACE,
            searchCriteria=search_criteria,
        )
        memory_records = []
        for summary in response["memoryRecordSummaries"]:
            memory_records.append(
                {
                    "content": summary["content"]["text"],
                    "id": summary["memoryRecordId"],
                    "score": summary["score"],
                    "metadata": {
                        "author": summary["metadata"]["author"]["stringValue"],
                        "namespace": summary["namespaces"][0],
                    },
                }
            )
        span.set_attribute("gen_ai.memory.record.count", len(memory_records))
        span.set_attribute("gen_ai.memory.records", json.dumps(memory_records))


def run_delete_memory_reference(client, memory_id, memory_record_id):
    """Scenario: AgentCore DeleteMemoryRecord."""
    print("  [delete_memory] Bedrock AgentCore DeleteMemoryRecord")
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "delete_memory",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.memory.store.id": memory_id,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "delete_memory", kind=SpanKind.CLIENT, attributes=span_attributes
    ) as span:
        span.set_attribute("gen_ai.memory.record.id", memory_record_id)
        span.set_attribute("gen_ai.memory.record.count", 1)
        client.delete_memory_record(
            memoryId=memory_id,
            memoryRecordId=memory_record_id,
        )


def run_delete_memory_store_reference(client, memory_id):
    """Scenario: Bedrock AgentCore delete_memory_store operation."""
    print("  [delete_memory_store] Bedrock AgentCore delete_memory_store")
    client_token = "delete-memory-store-token"
    host, port = mock_server_host_port(MOCK_BASE_URL)
    span_attributes = {
        "gen_ai.operation.name": "delete_memory_store",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.memory.store.id": memory_id,
    }
    if host:
        span_attributes["server.address"] = host
    if port is not None:
        span_attributes["server.port"] = port
    with _reference_tracer.start_as_current_span(
        "delete_memory_store", kind=SpanKind.CLIENT, attributes=span_attributes
    ):
        client.delete_memory(
            memoryId=memory_id,
            clientToken=client_token,
        )


def run_evaluation_reference(control_client, data_client):
    """Scenario: evaluation result event via AgentCore Evaluate, with the evaluator's rating scale."""
    print("  [evaluate] Bedrock AgentCore Evaluate")
    # The evaluator definition says whether it produces a number or picks a category.
    evaluator = control_client.get_evaluator(evaluatorId=EVALUATOR_ID)
    rating_scale = evaluator["evaluatorConfig"]["llmAsAJudge"]["ratingScale"]
    rating_scale_kind = "numerical" if "numerical" in rating_scale else "categorical"

    with _reference_tracer.start_as_current_span("reference.evaluation", kind=SpanKind.INTERNAL):
        response = data_client.evaluate(
            evaluatorId=EVALUATOR_ID,
            evaluationInput={"sessionSpans": [SESSION_SPAN]},
        )
        for result in response["evaluationResults"]:
            attributes = {
                "gen_ai.evaluation.name": result["evaluatorName"],
                "gen_ai.evaluation.score.rating_scale": rating_scale_kind,
            }
            if "value" in result:
                attributes["gen_ai.evaluation.score.value"] = result["value"]
            if "label" in result:
                attributes["gen_ai.evaluation.score.label"] = result["label"]
            if "explanation" in result:
                attributes["gen_ai.evaluation.explanation"] = result["explanation"]
            reference_event_logger("gen_ai.evaluation.reference").emit(
                event_name="gen_ai.evaluation.result",
                body="Evaluation result",
                attributes=attributes,
            )
            print(f"    -> {rating_scale_kind} score: {result.get('value')} ({result.get('label')})")


def main():
    print("=== Reference Implementation: AWS Bedrock AgentCore Memory and Evaluations ===")
    tp, lp, mp = setup_otel()

    control_client = create_agentcore_control_client()
    data_client = create_agentcore_data_client()
    memory_id = run_create_memory_store_reference(control_client)
    memory_record_id = run_create_and_update_memory_reference(data_client, memory_id)
    run_search_memory_reference(data_client, memory_id)
    run_delete_memory_reference(data_client, memory_id, memory_record_id)
    run_delete_memory_store_reference(control_client, memory_id)
    run_evaluation_reference(control_client, data_client)

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
