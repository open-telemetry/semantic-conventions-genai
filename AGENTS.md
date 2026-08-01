OpenTelemetry **GenAI semantic conventions**: spans, metrics, and events for
GenAI clients, MCP, and provider-specific conventions. Attributes live in
`model/<namespace>/registry.yaml`; signals in `model/<namespace>/{spans,metrics,events}.yaml`. Human docs are in `docs/gen-ai/`; runnable proofs in `reference/`.

## How to contribute conventions

1. **Be concise.** Short `brief`/`note` text. Small, focused PRs — phase large
   changes across several.
2. **Be actionable.** Tell instrumentation authors how to collect telemetry and
   consumers how to interpret it. Keep justification out of the conventions —
   put it in the PR description.
3. **Use this repo's terminology.** Reuse the established vocabulary —
   *operation*, *span*, *attribute*, *signal*, *inference*, *embeddings*,
   *execute tool*, *invoke agent* (client vs internal), *plan*, *memory*,
   *retrieval*, *workflow* — and existing `gen_ai.*` attribute names. When
   introducing a new concept, explain it and show how it maps across libraries
   and frameworks.
4. **No attribute without a signal.** Every attribute added must be referenced
   by a span, metric, or event that defines when and how it is recorded. No
   orphan attributes.
5. **No convention without a reference scenario.** A new convention
   needs a `reference/scenarios/<library>/` scenario that emits it. See
   [reference/CONTRIBUTING.md](reference/CONTRIBUTING.md).
6. **Only model what generic instrumentation can record at runtime.** A
   reference scenario must plausibly show how generic instrumentation captures
   the telemetry from information *available to it at runtime*. If it isn't
   instrumentable, don't propose conventions — open an issue and bring it to the
   [GenAI SIG](https://github.com/open-telemetry/community#sig-genai-instrumentation)
   or [#otel-genai-instrumentation](https://cloud-native.slack.com/archives/C06KR7ARS3X).
7. **Investigate breadth first.** Before adding a convention, survey the
   libraries/frameworks it applies to and the terminology and primitives *they*
   use. Propose something that works broadly across them, not for one SDK.
8. **Don't over-abstract.** If a broadly-applicable convention gets too
   abstract to be useful, prefer concrete framework-specific conventions over a
   forced generic concept.
9. **Stay in the GenAI domain.** This repo holds GenAI-related conventions. If a
   proposal is broader than GenAI, take it to
   [open-telemetry/semantic-conventions](https://github.com/open-telemetry/semantic-conventions).
## Workflow

```bash
make generate-all      # regenerate registry docs, embedded tables, reports — run after editing model

cd reference
uv run run-scenario <library>   # or --all; runs scenario, validates telemetry, writes data.json
```

CI fails if committed generated output doesn't match `make generate-all`. Add a
Towncrier fragment under [changelog.d/](changelog.d/) for any consumer-visible
change. See [CONTRIBUTING.md](CONTRIBUTING.md).

For PR work that needs repository-wide reference coverage, use the `reference`
skill under [.github/skills/reference/](.github/skills/reference/). For reviews
of reference coverage, capturability, and honest capture gaps, see the
evaluation rubric in
[.github/instructions/evaluate-reference.instructions.md](.github/instructions/evaluate-reference.instructions.md)
— an instruction file that applies automatically to model, docs, and scenario
changes, not a skill to invoke.

## Further reading

- [How to write conventions — best practices](https://github.com/open-telemetry/semantic-conventions/blob/v1.43.0/docs/how-to-write-conventions/README.md#best-practices)
- [Naming](https://github.com/open-telemetry/semantic-conventions/blob/v1.43.0/docs/general/naming.md)
- [Events](https://github.com/open-telemetry/semantic-conventions/blob/v1.43.0/docs/general/events.md)
- [Recording errors](https://github.com/open-telemetry/semantic-conventions/blob/v1.43.0/docs/general/recording-errors.md)
