# AGENTS

For local validation of a reference implementation in this repository, use
`uv run run-scenario <library>` from the `reference/` directory as the standard
command (equivalent to `python -m semconv_genai.run_scenario <library>`).

For semantic-conventions PR work that needs repository-wide reference coverage, use the `reference` skill under `.github/skills/reference/`.

For reviews of resulting reference coverage, capturability, and honest capture gaps, see the evaluation rubric in `.github/instructions/evaluate-reference.instructions.md`. It is an instruction file that applies automatically to model, docs, and scenario changes — not a skill to invoke.

Optimize all code in this repository for readability and simplicity.

- Avoid advanced syntax when an equivalent simpler form is available.
- Prefer straightforward control flow and explicit names over dense or compact constructs.
- Let errors bubble up and fail loudly. Do not swallow exceptions with try/except.
