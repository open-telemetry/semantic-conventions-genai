# Releasing

## Versions and schema URLs

Release `vX.Y.Z` publishes the development registry with schema URL
`https://opentelemetry.io/schemas/semconv-genai-dev/X.Y.Z-dev`.

`model/manifest.yaml` on `main` carries
`https://opentelemetry.io/schemas/semconv-genai-dev/X.Y.Z-unreleased`,
where `X.Y.Z` is the next release.

Each release has these assets:

- `manifest-dev.yaml` - publication manifest, served at the schema URL.
- `registry-dev.yaml` - resolved registry, referenced from the manifest.

## Preparing a release

1. Run the [prepare release workflow](.github/workflows/prepare-release.yml)
   with the version to release, e.g. `0.1.0`. It sets the release `schema_url`,
   renders a `## v{version}` section in [CHANGELOG.md](CHANGELOG.md) from
   [changelog.d/](changelog.d/), and opens a pull request labeled `release`.
2. Review and merge the pull request.

## Making the release

Merging the release pull request triggers the
[release workflow](.github/workflows/release.yml). It reads the topmost version
in `CHANGELOG.md`, creates the `v{version}` tag and publishes a GitHub release
with that changelog section and the assets. It then opens a pull request that
moves `main` to the next minor `-unreleased` version. Review and merge it.

On merge, the workflow only runs for pull requests with the `release` label.
It can also be run manually against `main` if the release pull request was
merged without triggering it. If only the bump job failed, re-run the failed
job.
