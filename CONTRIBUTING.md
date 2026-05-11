# Contributing

Welcome to the OpenTelemetry GenAI Semantic Conventions repository!

New to OpenTelemetry? Read the
[New Contributor Guide](https://github.com/open-telemetry/community/blob/main/guides/contributor/README.md)
first — it covers the CLA, Code of Conduct, and other prerequisites.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (or a compatible runtime
  such as Podman aliased as `docker`) — `make` runs Weaver via the
  `otel/weaver` container image.
- [GNU Make](https://www.gnu.org/software/make/) — pre-installed on macOS
  and Linux. On Windows, use [WSL](https://learn.microsoft.com/windows/wsl/install)
  or install via [Chocolatey](https://chocolatey.org/) (`choco install make`)
  or [Scoop](https://scoop.sh/) (`scoop install make`).

## Code structure

```
├── docs
│   ├── gen-ai/            # hand-written docs with embedded generated tables
│   └── registry/          # auto-generated attribute registry pages
├── model
│   └── <namespace>/       # e.g. gen-ai, mcp, openai
│       ├── registry.yaml  # attribute definitions
│       ├── spans.yaml     # span conventions
│       ├── metrics.yaml   # metric conventions
│       ├── events.yaml    # event conventions
│       └── deprecated/    # deprecated conventions
```

All attributes must be defined in `registry.yaml` files under the matching
namespace folder in `model/`.

## Making a change

### 1. Modify the YAML model

Refer to the
[Semantic Convention YAML Language](https://github.com/open-telemetry/weaver/blob/main/schemas/semconv-syntax.md)
to learn about the YAML file syntax.

### 2. Regenerate the docs

After updating the YAML, run:

```bash
make generate-all
```

This regenerates the attribute registry pages under `docs/registry/`,
refreshes the generated tables embedded in the hand-written docs under
`docs/gen-ai/`, and updates the committed schema snapshot under
`schema-snapshot/`.

### 3. Validate

Run the shared policy checks:

```bash
make check-policies
```

This validates the model against shared OpenTelemetry policies covering
naming conventions, attribute type rules, stability requirements, and
backwards compatibility.

### 4. Update reference scenarios

Changes under `model/` or `docs/` typically require updating the
reference scenarios under `reference/` to demonstrate that the proposed
updates are capturable. See
[reference/CONTRIBUTING.md](reference/CONTRIBUTING.md).

### 5. Update the changelog

Add an entry under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) for any
change to the conventions that a consumer would care about. Editorial
changes — typos, pure rewording, and repo tooling — don't need an entry.

## Keep PRs small

Small, focused PRs are much easier to review, and therefore much more
likely to land quickly. Consider phasing larger changes across multiple PRs
where possible.

If a PR review surfaces contentious or difficult points, consider splitting
those into follow-up PRs so the uncontroversial parts can land and each of the
harder points gets its own focused discussion and review.

## Asking questions

Post in
[#otel-genai-instrumentation](https://cloud-native.slack.com/archives/C06KR7ARS3X)
on [CNCF Slack](https://slack.cncf.io/) or join the next
[GenAI SIG](https://github.com/open-telemetry/community#sig-genai-instrumentation)
and add your topic to the
[meeting agenda](https://docs.google.com/document/d/1EKIeDgBGXQPGehUigIRLwAUpRGa7-1kXB736EaYuJ2M/edit).

## Approvers and Maintainers

### Maintainers

- [Liudmila Molkova](https://github.com/lmolkova), Grafana Labs
- [Trask Stalnaker](https://github.com/trask), Microsoft

For more information about the maintainer role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#maintainer).

### Approvers

- [Aaron Abbott](https://github.com/aabmass), Google
- [Ankit Singhal](https://github.com/singankit), Microsoft
- [JWinermaSplunk](https://github.com/JWinermaSplunk), Splunk
- [Mike Goldsmith](https://github.com/MikeGoldsmith), Honeycomb

For more information about the approver role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#approver).

Approvers assign themselves to non-editorial PRs
to signal that they will drive the review. A PR can have multiple
approvers assigned, and that is highly encouraged for medium and high
complexity PRs.

Over a rolling 3-month window, an approver is expected to sign up for and
drive the review of at least 3 non-editorial PRs.
"Driving the review" means staying engaged with the PR through to its
merge or close: providing timely initial reviews and follow-up feedback,
requesting changes, asking design questions, and re-reviewing revisions
promptly until the PR lands or is rejected.
