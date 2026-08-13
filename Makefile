# GenAI Semantic Conventions - Makefile
# Requires: either local weaver >= $(WEAVER_VERSION) OR docker/podman (aliased as docker)
# The weaver version is pinned in versions.env (WEAVER_VERSION) and run via
# the otel/weaver container image if a local weaver installation is not found.

# Shared external version pins. Override on the command line when needed, e.g.
# `make check-policies WEAVER_VERSION=v0.25.0`.
VERSION_PINS_FILE := versions.env
include $(VERSION_PINS_FILE)

# Run weaver locally if available, otherwise run via the pinned container image.
# The repo is bind-mounted at /workspace when running in Docker, resolving
# relative paths the same way they would on the host.
LOCAL_RAW_VERSION := $(shell weaver --version 2>/dev/null)

ifeq ($(LOCAL_RAW_VERSION),)
    USE_DOCKER := 1
else
    LOCAL_VERSION := $(shell echo "$(LOCAL_RAW_VERSION)" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?' | head -n1)
    REPO_VERSION := $(shell echo "$(WEAVER_VERSION)" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?' | head -n1)
    IS_LOWER := $(shell awk -v v1="$(LOCAL_VERSION)" -v v2="$(REPO_VERSION)" 'BEGIN { split(v1, a, "."); split(v2, b, "."); for (i = 1; i <= 3; i++) { if (a[i]+0 < b[i]+0) { print "yes"; exit }; if (a[i]+0 > b[i]+0) { print "no"; exit } }; print "no" }')
    ifeq ($(IS_LOWER),yes)
        $(warning local weaver version $(LOCAL_VERSION) is lower than required $(REPO_VERSION). Falling back to Docker.)
        USE_DOCKER := 1
    else
        USE_DOCKER := 0
    endif
endif

ifeq ($(USE_DOCKER),1)
WEAVER_IMAGE := otel/weaver:$(WEAVER_VERSION)
WEAVER := docker run --rm \
	-u $(shell id -u):$(shell id -g) \
	-v "$(CURDIR):/workspace" \
	-w /workspace \
	-e HOME=/tmp \
	$(WEAVER_IMAGE)
else
WEAVER := weaver
endif

# Baseline registry for the backwards-compatibility policy. Override on the
# command line to compare against a different ref or fork.
BASELINE_REGISTRY := https://github.com/trask/semantic-conventions-genai.git[model]

.PHONY: check-policies generate-registry generate-docs generate-json-schemas generate-all clean package-dev \
	generate-reference-reports update-upstream-links

# Upstream semantic-conventions version, derived from the pinned git tag in the
# model/manifest.yaml dependency (the single source of truth for that version).
SEMCONV_VERSION := $(shell grep -oE 'semantic-conventions\.git@v[0-9]+\.[0-9]+\.[0-9]+' model/manifest.yaml | sed 's/.*@//')

# Pinned upstream GitHub URL base, passed to templates as `upstream_docs_base`
# so cross-registry links to upstream pages resolve to the pinned version.
UPSTREAM_DOCS_BASE := https://github.com/open-telemetry/semantic-conventions/blob/$(SEMCONV_VERSION)

# Release version = last path segment of the top-level schema_url in
# model/manifest.yaml. E.g. `gen-ai-dev/1.42.0-dev` -> `1.42.0-dev`.
VERSION := $(shell awk '/^schema_url:/ { n = split($$2, parts, "/"); print parts[n]; exit }' model/manifest.yaml)
RESOLVED_SCHEMA_URI := https://github.com/open-telemetry/semantic-conventions-genai/releases/download/v$(VERSION)/resolved.yaml
PACKAGE_OUTPUT := .build/package

# Validate the model and run shared policies from otel-weaver-packages.
check-policies:
	$(WEAVER) registry check \
		-r ./model \
		--v2 \
		--policy '$(POLICY_REPO_URL)@$(POLICY_REPO_REF)[policies/check]' \
		--policy policies/check/json-schema-annotations
		# --baseline-registry '$(BASELINE_REGISTRY)' \ uncomment after removing deprecated entries

# Generate the attribute registry pages under docs/registry/ from local
# templates that consume the v2 resolved registry.
generate-registry:
	$(WEAVER) registry generate \
		-r ./model \
		--v2 \
		-t ./templates/registry \
		--param upstream_docs_base=$(UPSTREAM_DOCS_BASE) \
		markdown \
		./docs/registry

# Refresh the weaver snippet tables embedded in hand-written signal docs under
# docs/gen-ai/ (rewritten in place between <!-- weaver ... --> markers).
generate-docs:
	$(WEAVER) registry update-markdown \
		-r ./model \
		--v2 \
		-t ./templates \
		--target markdown \
		--param registry_base_url=/docs/registry/ \
		--param upstream_docs_base=$(UPSTREAM_DOCS_BASE) \
		docs

# Rewrite hardcoded upstream links in model and docs text to $(SEMCONV_VERSION).
# Templates resolve their own links via `upstream_docs_base`, but links written
# by hand in model `brief`/`note` text are published to downstream consumers, so
# they have to be real URLs rather than a placeholder.
update-upstream-links:
	.github/scripts/update-upstream-links.sh $(SEMCONV_VERSION)

# Regenerate the JSON schemas under model/gen-ai/ from the pydantic models in
# docs/gen-ai/non-normative/models.py.
generate-json-schemas:
	cd docs/gen-ai/non-normative && uv run models.py $(CURDIR)/model/gen-ai

# Update reference reports (README.md and reports/) from data.json files.
generate-reference-reports:
	cd reference && uv run --frozen update-reports

# Run every regeneration the repo owns (weaver-driven + pydantic-driven + reports).
# CI checks that all committed outputs match what this target generates.
generate-all: update-upstream-links generate-registry generate-docs generate-json-schemas generate-reference-reports

# Package the registry into a publication artifact. The version comes from
# model/manifest.yaml's schema_url; bump it there to cut a new release.
package-dev:
	@mkdir -p .build
	rm -rf $(PACKAGE_OUTPUT)
	$(WEAVER) registry package \
		-r ./model \
		--v2 \
		--resolved-schema-uri '$(RESOLVED_SCHEMA_URI)' \
		-o ./$(PACKAGE_OUTPUT)
	@echo "Packaged version $(VERSION) -> $(PACKAGE_OUTPUT)"

# Remove generated docs, the local .build/ tree (Weaver-fetched templates/policies
# plus any hand-created weaver-min-repro* dirs), reference-project caches, and
# Python bytecode trees under the entire repo.
#
# `clean` does NOT touch `reference/.venv`; rebuilding it requires a fresh
# `uv sync` which re-downloads every tooling dependency. Remove it manually
# (`rm -rf reference/.venv`) for a full reset.
clean:
	rm -rf docs/registry
	rm -rf .build
	rm -rf reference/.cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
