"""Reference implementation for LangGraph durable state updates."""

import asyncio
from typing import TypedDict
from uuid import UUID

from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

_reference_tracer = reference_tracer()


class ExecutionState(TypedDict, total=False):
    approval_status: str


async def run_durable_workflow_reference() -> None:
    """Run a persisted LangGraph workflow across an interrupt and resume."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.runtime import ExecutionInfo, Runtime
    from langgraph.types import Command, interrupt

    execution_infos: list[ExecutionInfo] = []

    def wait_for_approval(state: ExecutionState, runtime: Runtime) -> ExecutionState:
        execution_info = runtime.execution_info
        if execution_info is None or execution_info.thread_id is None:
            raise RuntimeError("LangGraph did not provide durable execution information")
        execution_infos.append(execution_info)

        interrupt("approval-required")
        return {"approval_status": "approved"}

    builder = StateGraph(ExecutionState)
    builder.add_node("wait_for_approval", wait_for_approval)
    builder.add_edge(START, "wait_for_approval")
    builder.add_edge("wait_for_approval", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    thread_id = "langgraph-durable-reference-thread"
    initial_config = {
        "configurable": {"thread_id": thread_id},
        "run_id": UUID("10000000-0000-4000-8000-000000000001"),
    }
    resumed_config = {
        "configurable": {"thread_id": thread_id},
        "run_id": UUID("10000000-0000-4000-8000-000000000002"),
    }

    with _reference_tracer.start_as_current_span(
        "invoke_workflow durable approval workflow",
        attributes={
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.workflow.name": "durable approval workflow",
        },
    ):
        suspended_result = await graph.ainvoke({}, config=initial_config)
        if not suspended_result.get("__interrupt__") or len(execution_infos) != 1:
            raise RuntimeError("LangGraph did not suspend the persisted execution")
        suspended_execution_info = execution_infos[0]
        suspended_snapshot = await graph.aget_state(initial_config)
        suspended_checkpoint_id = suspended_snapshot.config["configurable"].get("checkpoint_id")
        if not isinstance(suspended_checkpoint_id, str):
            raise RuntimeError("LangGraph did not expose a checkpoint ID before suspension")

    with _reference_tracer.start_as_current_span(
        "invoke_workflow durable approval workflow",
        attributes={
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.workflow.name": "durable approval workflow",
        },
    ):
        resumed_updates = [
            update async for update in graph.astream(Command(resume=True), config=resumed_config, stream_mode="updates")
        ]
        if len(execution_infos) != 2:
            raise RuntimeError("LangGraph did not expose execution information after resume")
        resumed_execution_info = execution_infos[1]
        if resumed_execution_info.thread_id != suspended_execution_info.thread_id:
            raise RuntimeError("LangGraph resumed a different durable execution")
        if (
            suspended_execution_info.run_id is not None
            and resumed_execution_info.run_id is not None
            and suspended_execution_info.run_id == resumed_execution_info.run_id
        ):
            raise RuntimeError("LangGraph did not expose a distinct run ID for the resumed call")

        if len(resumed_updates) != 1:
            raise RuntimeError("LangGraph did not expose one resumed node state update")
        node_delta = resumed_updates[0].get("wait_for_approval")
        if not isinstance(node_delta, dict) or not node_delta:
            raise RuntimeError("LangGraph did not expose the resumed node state delta")

        resumed_snapshot = await graph.aget_state(resumed_config)
        if resumed_snapshot.values.get("approval_status") != "approved":
            raise RuntimeError("LangGraph did not persist the resumed node state update")
        resumed_checkpoint_id = resumed_snapshot.config["configurable"].get("checkpoint_id")
        if not isinstance(resumed_checkpoint_id, str):
            raise RuntimeError("LangGraph did not expose a checkpoint ID after resume")
        if resumed_checkpoint_id == suspended_checkpoint_id:
            raise RuntimeError("LangGraph did not advance the persisted state version")

        reference_event_logger().emit(
            event_name="gen_ai.execution.state.changed",
            body="Execution state changed",
            attributes={
                "gen_ai.execution.state.changed_key.count": len(node_delta),
                "gen_ai.execution.state.changed_keys": sorted(node_delta),
                "gen_ai.execution.state.version": resumed_checkpoint_id,
            },
        )


def main() -> None:
    print("=== Reference Implementation: LangGraph ===")
    tp, lp, mp = setup_otel()
    asyncio.run(run_durable_workflow_reference())
    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
