# Changelog Fragments

Add one Towncrier fragment for each convention change that consumers should
notice. Editorial changes, typo fixes, pure rewording, and repo tooling changes
do not need fragments.

Fragment filenames use this form:

```text
<pr-number>.<type>.md
```

Use `<pr-number>.<type>.<counter>.md` when one pull request needs multiple
fragments of the same type. Use `+.<type>.md` or `+.<type>.<counter>.md` only
when there is no pull request number yet.

Supported types:

- `breaking` - breaking changes
- `deprecation` - deprecations
- `component` - new components
- `enhancement` - enhancements
- `bugfix` - bug fixes
- `clarification` - clarifications

Preview the next changelog section with:

```bash
VERSION=$(awk '/^schema_url:/ { n = split($2, parts, "/"); print parts[n]; exit }' model/manifest.yaml)
PYTHONUTF8=1 uv run --project changelog.d --locked towncrier build --config changelog.d/towncrier.toml --draft --version "$VERSION"
```
