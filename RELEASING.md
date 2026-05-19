# Releasing

Releases are cut from `main` and published as GitHub Releases with the
publication manifest and resolved schema attached as assets. The dev channel
uses tags of the form `vX.Y.Z-dev`; the schema URL lives under
`https://opentelemetry.io/schemas/gen-ai-dev/X.Y.Z-dev`.

1. Open a release-prep pull request that:
   - Bumps the top-level `schema_url` in [model/manifest.yaml](model/manifest.yaml)
     to the new version (e.g. `https://opentelemetry.io/schemas/gen-ai-dev/1.43.0-dev`).
   - Updates [CHANGELOG.md](CHANGELOG.md):
     - Renames the existing `## Unreleased` section to the new version
       (e.g. `## 1.43.0-dev`), removing any empty subsections.
     - Adds a new `## Unreleased` section at the top with empty subsections.
2. Get the PR reviewed and merged to `main`.
3. Prepare a [draft release](https://github.com/open-telemetry/semantic-conventions-genai/releases/new):
   - Tag: `vX.Y.Z-dev` matching the bumped `schema_url` (choose "Create new tag on publish").
   - Description: copy the changelog entries for this version.
   - **Save as draft** — do not publish.
4. Run the [Release (dev) workflow](https://github.com/open-telemetry/semantic-conventions-genai/actions/workflows/release-dev.yml).
   It will attach resolved schema artifacts and publish the draft as a prerelease,
   creating the git tag at the workflow's commit.
