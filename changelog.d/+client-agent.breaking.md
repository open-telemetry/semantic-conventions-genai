Add `gen_ai.client.invoke_agent.duration` metric, move invoke agent client span and metric to `client-agent.md`.

Invoke agent client operations are no longer reported on `gen_ai.client.operation.duration` - use `gen_ai.client.invoke_agent.duration` instead.
