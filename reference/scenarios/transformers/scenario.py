"""Reference server timing for Transformers Serve."""

import asyncio
import json
from contextvars import ContextVar
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import httpx
import torch
from reference_shared import flush_and_shutdown, reference_meter, setup_otel
from starlette.responses import JSONResponse, StreamingResponse
from starlette.types import Message, Receive, Scope, Send
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedModel, PreTrainedTokenizerFast, ProcessorMixin
from transformers.cli.serving import server
from transformers.cli.serving import utils as serving_utils
from transformers.cli.serving.chat_completion import ChatCompletionHandler
from transformers.cli.serving.completion import CompletionHandler
from transformers.cli.serving.model_manager import ModelManager
from transformers.cli.serving.response import ResponseHandler
from transformers.cli.serving.systemone import SystemOneHandler
from transformers.cli.serving.transcription import TranscriptionHandler
from transformers.cli.serving.utils import DirectStreamer, GenerationState

_reference_meter = reference_meter()
_request_duration = _reference_meter.create_histogram(
    "gen_ai.server.request.duration",
    unit="s",
    description="Duration of a model server request.",
    explicit_bucket_boundaries_advisory=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
)
_time_to_first_token = _reference_meter.create_histogram(
    "gen_ai.server.time_to_first_token",
    unit="s",
    description="Time to generate the first output token.",
    explicit_bucket_boundaries_advisory=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)
_time_per_output_token = _reference_meter.create_histogram(
    "gen_ai.server.time_per_output_token",
    unit="s",
    description="Time per output token generated after the first token.",
    explicit_bucket_boundaries_advisory=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
)


@dataclass
class TokenTiming:
    first_token_at: float | None = None
    output_tokens: int = 0
    completed: bool = False
    response_model: str | None = None


_token_timing = ContextVar[TokenTiming | None]("token_timing", default=None)


class ReferenceStreamer(DirectStreamer):
    def __init__(self, tokenizer, loop, queue, response_parser=None):
        super().__init__(tokenizer, loop, queue, response_parser=response_parser)
        # The server creates the streamer on the request thread and calls put on the inference thread.
        self._timing = _token_timing.get()

    def put(self, value: torch.Tensor) -> None:
        generated_at = perf_counter()
        super().put(value)
        if self._timing is not None and self.total_tokens > 0:
            if self._timing.first_token_at is None:
                self._timing.first_token_at = generated_at
            self._timing.output_tokens = self.total_tokens

    def end(self) -> None:
        if self._timing is not None:
            self._timing.completed = True
        super().end()


class ReferenceStreamingResponse(StreamingResponse):
    def __init__(
        self, response: StreamingResponse, started_at: float, timing: TokenTiming, attributes: dict[str, str | int]
    ) -> None:
        super().__init__(
            response.body_iterator,
            status_code=response.status_code,
            media_type=response.media_type,
            background=response.background,
        )
        self.raw_headers = response.raw_headers
        self.started_at = started_at
        self.timing = timing
        self.metric_attributes = attributes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response_finished = False

        async def send_body(message: Message) -> None:
            nonlocal response_finished
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_finished = True

        attributes = self.metric_attributes
        if self.timing.response_model is not None:
            attributes["gen_ai.response.model"] = self.timing.response_model
        endpoint = scope.get("server")
        if endpoint is not None and endpoint[1] is not None:
            attributes["server.address"], attributes["server.port"] = endpoint

        error_type: str | None = None
        try:
            await super().__call__(scope, receive, send_body)
        except (asyncio.CancelledError, Exception) as error:
            error_type = type(error).__qualname__
            raise
        else:
            if not response_finished:
                error_type = "client_disconnected"
            elif not self.timing.completed:
                error_type = "generation_failed"
        finally:
            duration = perf_counter() - self.started_at
            duration_attributes = attributes if error_type is None else attributes | {"error.type": error_type}
            _request_duration.record(duration, duration_attributes)

        if error_type is None and self.timing.first_token_at is not None:
            ttft = self.timing.first_token_at - self.started_at
            _time_to_first_token.record(ttft, attributes)
            if self.timing.output_tokens > 1:
                _time_per_output_token.record((duration - ttft) / (self.timing.output_tokens - 1), attributes)


class ReferenceCompletionHandler(CompletionHandler):
    def _resolve_model(self, body: dict) -> tuple[str, PreTrainedModel, ProcessorMixin | PreTrainedTokenizerFast]:
        model_id, model, processor = super()._resolve_model(body)
        timing = _token_timing.get()
        if timing is not None:
            timing.response_model = model_id
        return model_id, model, processor

    async def handle_request(self, body: dict, request_id: str) -> StreamingResponse | JSONResponse:
        started_at = perf_counter()
        timing = TokenTiming()
        attributes: dict[str, str | int] = {
            "gen_ai.operation.name": "text_completion",
            "gen_ai.provider.name": "transformers",
        }
        error_type: str | None = None
        context = _token_timing.set(timing)
        try:
            response = await super().handle_request(body, request_id)
        except (asyncio.CancelledError, Exception) as error:
            error_type = type(error).__qualname__
            raise
        finally:
            _token_timing.reset(context)
            request_model = body.get("model")
            if isinstance(request_model, str):
                attributes["gen_ai.request.model"] = request_model
            if error_type is not None and body.get("stream"):
                _request_duration.record(perf_counter() - started_at, attributes | {"error.type": error_type})
        if not isinstance(response, StreamingResponse):
            return response

        return ReferenceStreamingResponse(response, started_at, timing, attributes)


def save_tiny_model(path: Path) -> None:
    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "red": 1, "blue": 2}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]", pad_token="[UNK]").save_pretrained(path)
    config = GPT2Config(
        vocab_size=tokenizer.get_vocab_size(),
        n_positions=32,
        n_embd=16,
        n_layer=1,
        n_head=2,
        pad_token_id=0,
        bos_token_id=None,
        eos_token_id=None,
    )
    GPT2LMHeadModel(config).save_pretrained(path)


async def run_completion(model_path: Path) -> None:
    model_manager = ModelManager(device="cpu")
    generation_state = GenerationState()
    fastapi_without_telemetry = partial(
        server.FastAPI,
        telemetry={"tracing": False, "metrics": False, "logs": False},
    )
    with patch.object(server, "FastAPI", fastapi_without_telemetry):
        app = server.build_server(
            model_manager,
            ChatCompletionHandler(model_manager, generation_state),
            ReferenceCompletionHandler(model_manager, generation_state),
            ResponseHandler(model_manager, generation_state),
            TranscriptionHandler(model_manager, generation_state),
            SystemOneHandler(model_manager, generation_state),
            generation_state,
        )
    with patch.object(serving_utils, "DirectStreamer", ReferenceStreamer):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client,
        ):
            response = await client.post(
                "/v1/completions",
                json={
                    "model": str(model_path),
                    "prompt": "red blue",
                    "max_tokens": 4,
                    "temperature": 0,
                    "stream": True,
                },
            )
            invalid_response = await client.post(
                "/v1/completions",
                json={"model": str(model_path), "prompt": ["red blue"], "stream": True},
            )
    response.raise_for_status()
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    assert events[-1]["usage"]["completion_tokens"] == 4, events
    assert invalid_response.status_code == 400, invalid_response.text


def main() -> None:
    tp, lp, mp = setup_otel()
    torch.manual_seed(0)
    torch.set_num_threads(1)
    try:
        with TemporaryDirectory() as directory:
            model_path = Path(directory) / "tiny-gpt2"
            save_tiny_model(model_path)
            asyncio.run(run_completion(model_path))
    finally:
        flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
