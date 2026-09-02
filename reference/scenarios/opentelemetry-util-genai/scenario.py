"""Reference implementation for opentelemetry-util-genai content storage."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from opentelemetry import context
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai import types
from opentelemetry.util.genai._upload.completion_hook import (
    CompletionRefs,
    JsonEncodeable,
    UploadCompletionHook,
    UploadData,
)
from reference_shared import flush_and_shutdown, reference_event_logger, reference_tracer, setup_otel

_reference_tracer = reference_tracer()
_upload_logger = logging.getLogger("opentelemetry.util.genai._upload.completion_hook")


class _DroppedUploadHandler(logging.Handler):
    """Translate the upload hook's real queue-admission rejection."""

    def __init__(self, hook: "ReceiptUploadCompletionHook") -> None:
        super().__init__()
        self._hook = hook

    def emit(self, record: logging.LogRecord) -> None:
        if record.msg != "upload queue is full, dropping upload %s" or not record.args:
            return
        path = record.args[0] if isinstance(record.args, tuple) else record.args
        if isinstance(path, str):
            reference_attribute, receipt_context = self._hook.receipt_context(path)
            token = context.attach(receipt_context)
            try:
                reference_event_logger().emit(
                    event_name="gen_ai.content.storage.result",
                    body="GenAI content storage result",
                    severity_number=SeverityNumber.WARN,
                    attributes={
                        reference_attribute: path,
                        "gen_ai.content.storage.status": "dropped",
                    },
                )
            finally:
                context.detach(token)


class ReceiptUploadCompletionHook(UploadCompletionHook):
    """Instrument the hook's real terminal write result."""

    def __init__(self, *, base_path: str, max_queue_size: int, block_uploads: bool) -> None:
        super().__init__(base_path=base_path, max_queue_size=max_queue_size)
        self._release_upload = threading.Event()
        if not block_uploads:
            self._release_upload.set()
        self._receipt_context: dict[str, tuple[str, context.Context]] = {}
        self._dropped_upload_handler = _DroppedUploadHandler(self)

    def _calculate_ref_path(
        self,
        system_instruction: list[types.MessagePart],
        tool_definitions: list[types.ToolDefinition] | None = None,
    ) -> CompletionRefs:
        refs = super()._calculate_ref_path(system_instruction, tool_definitions)
        current_context = context.get_current()
        self._receipt_context[refs.inputs_ref] = (
            "gen_ai.input.messages_ref",
            current_context,
        )
        self._receipt_context[refs.outputs_ref] = (
            "gen_ai.output.messages_ref",
            current_context,
        )
        self._receipt_context[refs.system_instruction_ref] = (
            "gen_ai.system_instructions_ref",
            current_context,
        )
        return refs

    def _submit_all(self, upload_data: UploadData) -> None:
        _upload_logger.addHandler(self._dropped_upload_handler)
        try:
            super()._submit_all(upload_data)
        finally:
            _upload_logger.removeHandler(self._dropped_upload_handler)

    def receipt_context(self, path: str) -> tuple[str, context.Context]:
        return self._receipt_context[path]

    def _do_upload(
        self,
        path: str,
        contents_hashed_to_filename: bool,
        json_encodeable: Callable[[], JsonEncodeable],
    ) -> None:
        if not self._release_upload.wait(timeout=5):
            raise TimeoutError("reference scenario did not release upload")

        try:
            super()._do_upload(path, contents_hashed_to_filename, json_encodeable)
        except Exception as error:
            reference_attribute, receipt_context = self._receipt_context[path]
            token = context.attach(receipt_context)
            try:
                reference_event_logger().emit(
                    event_name="gen_ai.content.storage.result",
                    body="GenAI content storage result",
                    severity_number=SeverityNumber.WARN,
                    attributes={
                        reference_attribute: path,
                        "gen_ai.content.storage.status": "failed",
                        "error.type": type(error).__qualname__,
                    },
                )
            finally:
                context.detach(token)
            raise
        else:
            reference_attribute, receipt_context = self._receipt_context[path]
            token = context.attach(receipt_context)
            try:
                reference_event_logger().emit(
                    event_name="gen_ai.content.storage.result",
                    body="GenAI content storage result",
                    severity_number=SeverityNumber.INFO,
                    attributes={
                        reference_attribute: path,
                        "gen_ai.content.storage.status": "stored",
                    },
                )
            finally:
                context.detach(token)

    def release_upload(self) -> None:
        self._release_upload.set()


def run_stored_and_dropped_content_storage() -> None:
    """Store one object and reject two from the hook's bounded queue."""
    print("  [content_storage] stored and queue-dropped content")

    with TemporaryDirectory() as upload_dir:
        hook = ReceiptUploadCompletionHook(
            base_path=upload_dir,
            max_queue_size=1,
            block_uploads=True,
        )
        with _reference_tracer.start_as_current_span(
            "chat",
            kind=SpanKind.CLIENT,
            attributes={"gen_ai.operation.name": "chat"},
        ) as span:
            hook.on_completion(
                inputs=[types.InputMessage(role="user", parts=[types.Text(content="Weather in Paris?")])],
                outputs=[
                    types.OutputMessage(
                        role="assistant",
                        parts=[types.Text(content="The weather in Paris is rainy.")],
                        finish_reason="stop",
                    )
                ],
                system_instruction=[types.Text(content="Answer weather questions concisely.")],
                span=span,
            )

        hook.release_upload()
        hook.shutdown(timeout_sec=5)


def run_failed_content_storage() -> None:
    """Fail a real local-filesystem write after hook initialization succeeds."""
    print("  [content_storage] failed content write")

    with TemporaryDirectory() as upload_root:
        removed_upload_dir = Path(upload_root) / "removed-before-upload"
        removed_upload_dir.mkdir()
        hook = ReceiptUploadCompletionHook(
            base_path=str(removed_upload_dir),
            max_queue_size=1,
            block_uploads=False,
        )
        removed_upload_dir.rmdir()

        with _reference_tracer.start_as_current_span(
            "chat",
            kind=SpanKind.CLIENT,
            attributes={"gen_ai.operation.name": "chat"},
        ) as span:
            hook.on_completion(
                inputs=[types.InputMessage(role="user", parts=[types.Text(content="Will this be stored?")])],
                outputs=[],
                system_instruction=[],
                span=span,
            )

        hook.shutdown(timeout_sec=5)


def main() -> None:
    print("=== Reference Implementation: opentelemetry-util-genai ===")
    tp, lp, mp = setup_otel()

    run_stored_and_dropped_content_storage()
    run_failed_content_storage()

    flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
