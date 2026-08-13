#!/bin/bash
#
# Rewrite pinned links into open-telemetry/semantic-conventions so they match
# the upstream version this repo depends on.
#
# Model YAML is published and consumed directly by downstream repos, so links
# in `brief` and `note` text have to be real URLs rather than a template
# placeholder. That leaves the version duplicated across every link, so this
# script rewrites them all from the single source of truth: the pinned git tag
# in the `model/manifest.yaml` dependency.
#
# Run via `make update-upstream-links`, which `make generate-all` includes. CI
# fails if committed files do not match what this produces.
#
# Usage: update-upstream-links.sh v1.44.0

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $(basename "$0") <version>, e.g. v1.44.0" >&2
  echo "run \`make update-upstream-links\`, which derives the version from model/manifest.yaml" >&2
  exit 1
fi

VERSION=$1

URL_PREFIX="https://github.com/open-telemetry/semantic-conventions/blob/"

find model docs AGENTS.md -type f \( -name '*.yaml' -o -name '*.md' \) -print0 |
  while IFS= read -r -d '' file; do
    perl -pi -e "s,\Q${URL_PREFIX}\Ev\d+\.\d+\.\d+,${URL_PREFIX}${VERSION},g" "$file"
  done
