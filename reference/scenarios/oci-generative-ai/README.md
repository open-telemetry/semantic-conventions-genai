# oci-generative-ai

OCI Generative AI exposes an OpenAI-compatible endpoint at
`https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1`, so the
stock `openai` SDK pointed at it is a **model-call boundary**: it calls the model
directly and owns inference. There is no OCI-specific client class; the provider
is recognised from the client's `base_url` host (suffix `.oci.oraclecloud.com`),
the same way `AzureOpenAI` is recognised from its client class. The mock server
stands in for that host here.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes — calls the model directly | ✅ Implemented |
| embeddings | Yes — OCI serves embedding models, but they are not exposed on the OpenAI-compatible surface this scenario exercises | ❌ Not implemented |
| execute_tool | No — the client doesn't execute tools; the tool runs in app code | ➖ Not instrumentable |
