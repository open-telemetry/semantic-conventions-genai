# Releasing

## Versions and schema URLs

Release `vX.Y.Z` publishes the development registry with schema URL
`https://opentelemetry.io/schemas/semconv-genai-dev/X.Y.Z-dev`.

`model/manifest.yaml` on `main` carries
`https://opentelemetry.io/schemas/semconv-genai-unreleased/X.Y.Z-unreleased`,
where `X.Y.Z` is the next release.

Each release has these assets:

- `manifest-dev.yaml` - publication manifest, served at the schema URL.
- `registry-dev.yaml` - resolved registry, referenced from the manifest.

## Making a release

1. Run the [Prepare release](.github/workflows/prepare-release.yml)
   workflow. It uses the version from `model/manifest.yaml` unless one is provided.
   It opens a pull request that sets the release `schema_url` and renders
   [CHANGELOG.md](CHANGELOG.md) from [changelog.d/](changelog.d/).
2. Review and merge the pull request.

Merging runs the [Release](.github/workflows/release.yml)
workflow. It tags the merge commit, publishes the GitHub release with the
changelog section and the assets, and opens a pull request bumping `main` to the
next minor `-unreleased` version. Review and merge it.

If the Release workflow fails, use **Re-run failed jobs**. If the fix needs a
workflow change and the release isn't published yet, run the workflow manually
with the version and the merge commit SHA.
