# azure-ai-contentsafety

The Azure AI Content Safety SDK calls a remote content-analysis service. The
`analyze_text` operation owns a client boundary and returns provider-native
category severities and blocklist matches. It does not return an overall
allow/deny verdict or caller enforcement action.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| apply_guardrail | Yes - `ContentSafetyClient.analyze_text` calls the remote service | Implemented |
| guardrail result event | Yes - the response contains category and blocklist results | Implemented |
| inference | No - the SDK does not call a model for generation | Not instrumentable |

Every emitted value comes from `AnalyzeTextOptions`, `AnalyzeTextResult`, or
the configured SDK endpoint. The scenario does not infer allow or deny from
Azure severity values.
