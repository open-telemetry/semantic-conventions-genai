Add `gen_ai.client.fetch_response.duration` metric, move fetch response span and metric to `client-fetch-response.md`.

Fetch response operations are no longer reported on `gen_ai.client.operation.duration` - use `gen_ai.client.fetch_response.duration` instead.
