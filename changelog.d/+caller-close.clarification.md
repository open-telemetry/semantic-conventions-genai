Report `interrupted` instead of `error` when a stream ends gracefully before a finish reason arrives, including when a caller closes or disposes it, and for fetched responses with `cancelled` status.
