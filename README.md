# <img src="https://opentelemetry.io/img/logos/opentelemetry-logo-nav.png" alt="OpenTelemetry Icon" width="45"> OpenTelemetry GenAI Semantic Conventions

Semantic Conventions for Generative AI (GenAI), including spans, metrics,
and events for GenAI clients, MCP (Model Context Protocol), and
provider-specific conventions (OpenAI, etc.).

This repository extends the
[OpenTelemetry Semantic Conventions](https://github.com/open-telemetry/semantic-conventions)
with GenAI-specific conventions, using
[Weaver](https://github.com/open-telemetry/weaver) to manage dependencies
on the core semantic conventions.

## Schema URL

TODO

## Read the docs

The human-readable version of the semantic conventions resides in the
[docs](docs/) folder. Major parts of these Markdown documents are generated
from the YAML definitions located in the [model](model/) folder.

Reference implementations and their tooling live under [reference](reference/).
For the Python reference compliance matrix and per-signal support reports, see
[reference/README.md](reference/README.md).
For contribution guidance specific to that project, see
[reference/CONTRIBUTING.md](reference/CONTRIBUTING.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
