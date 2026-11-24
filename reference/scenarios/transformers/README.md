# transformers

Transformers Serve owns model loading, request handling, and token generation for its OpenAI-compatible endpoints. This scenario sends a successful and a rejected streaming text completion request to the real ASGI app using a tiny local GPT-2 model on CPU.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| `gen_ai.server.request.duration` | Yes - completion handler entry through stream completion, failure, or disconnect | ✅ Implemented |
| `gen_ai.server.time_to_first_token` | Yes - first generated token observed by the server's `DirectStreamer` | ✅ Implemented |
| `gen_ai.server.time_per_output_token` | Yes - server request time after the first token, divided by the remaining generated tokens | ✅ Implemented |

`DirectStreamer` counts model output tokens before decoding them to text. The scenario doesn't use SSE chunks to count tokens or measure time to first token. A request that fails before streaming or has a failed or interrupted stream records request duration with `error.type`, but neither token histogram.

The scenario reads the server address and port from the ASGI scope for both completed and rejected requests. The streaming response records the canonical model ID that Transformers Serve puts in completion events.
